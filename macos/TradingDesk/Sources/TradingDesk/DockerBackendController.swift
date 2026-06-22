import Foundation
import Observation

/// Manages the engine backend, which runs as a Docker container.
///
/// On launch: locate Docker → ensure the `tradingdesk-engine:dev` image exists
/// (load the image shipped inside the app, or build it in dev) → `docker compose
/// up -d desk-server` → poll `/health`. On quit: stop the service. The user
/// configures nothing; the one prerequisite is Docker Desktop being installed.
@MainActor
@Observable
final class DockerBackendController {
    /// Shared instance so the AppDelegate can stop the backend on quit while the
    /// UI observes the same controller (see TradingDeskApp / RootSplitView).
    static let shared = DockerBackendController()

    enum State: Equatable {
        case idle
        case checkingDocker
        case dockerMissing
        case preparingImage
        case starting
        case ready
        case failed(String)
        case stopped
    }

    private(set) var state: State = .idle
    private(set) var detail: String = ""

    let baseURL = DeskBackend.baseURL
    private let imageTag = "tradingdesk-engine:dev"

    private var dockerPath: String?
    private var composeFile: String?

    // MARK: lifecycle

    func start() async {
        state = .checkingDocker
        detail = "looking for Docker…"
        guard let docker = Self.findDocker() else {
            state = .dockerMissing
            detail = "Docker Desktop not found. Install it from docker.com, then relaunch."
            return
        }
        dockerPath = docker

        let (verStatus, _) = await Self.runProcess(docker, ["version", "--format", "{{.Server.Version}}"])
        if verStatus != 0 {
            state = .dockerMissing
            detail = "Docker is installed but the daemon isn't running. Start Docker Desktop and relaunch."
            return
        }

        guard let compose = Self.findComposeFile() else {
            state = .failed("docker-compose.yml not found")
            detail = "Could not locate the compose file."
            return
        }
        composeFile = compose
        let composeDir = (compose as NSString).deletingLastPathComponent

        // Ensure the image exists: prefer the one shipped in the app; else build (dev).
        state = .preparingImage
        let (inspect, _) = await Self.runProcess(docker, ["image", "inspect", imageTag])
        if inspect != 0 {
            if let tar = Self.bundledImageTar() {
                detail = "loading bundled engine image…"
                let (loaded, out) = await Self.runProcess(docker, ["load", "-i", tar])
                if loaded != 0 {
                    state = .failed("docker load failed")
                    detail = String(out.prefix(300))
                    return
                }
            } else {
                detail = "building engine image (first run, dev)…"
                let (built, out) = await Self.runProcess(
                    docker, ["compose", "-f", compose, "build", "desk-server"], cwd: composeDir
                )
                if built != 0 {
                    state = .failed("image build failed")
                    detail = String(out.suffix(300))
                    return
                }
            }
        }

        state = .starting
        detail = "starting backend container…"
        let (up, upOut) = await Self.runProcess(
            docker, ["compose", "-f", compose, "up", "-d", "desk-server"], cwd: composeDir
        )
        if up != 0 {
            state = .failed("compose up failed")
            detail = String(upOut.suffix(300))
            return
        }

        detail = "waiting for backend health…"
        if await waitForHealth(timeoutSeconds: 90) {
            state = .ready
            detail = "backend ready at \(baseURL.absoluteString)"
        } else {
            state = .failed("backend did not become healthy in time")
        }
    }

    func stop() async {
        guard let docker = dockerPath, let compose = composeFile else { return }
        let composeDir = (compose as NSString).deletingLastPathComponent
        _ = await Self.runProcess(docker, ["compose", "-f", compose, "stop", "desk-server"], cwd: composeDir)
        state = .stopped
    }

    // MARK: health

    func waitForHealth(timeoutSeconds: Int) async -> Bool {
        let deadline = Date().addingTimeInterval(TimeInterval(timeoutSeconds))
        while Date() < deadline {
            if await healthOK() { return true }
            try? await Task.sleep(for: .seconds(2))
        }
        return false
    }

    private func healthOK() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("health"))
        req.timeoutInterval = 3
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return false }
        return (obj["status"] as? String) == "ok"
    }

    // MARK: helpers (nonisolated — no actor state)

    nonisolated static func findDocker() -> String? {
        let candidates = [
            "/usr/local/bin/docker",
            "/opt/homebrew/bin/docker",
            "/Applications/Docker.app/Contents/Resources/bin/docker",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// The compose file: an explicit override, the app bundle's Resources, or
    /// the nearest `docker-compose.yml` walking up from the executable (dev).
    nonisolated static func findComposeFile() -> String? {
        let fm = FileManager.default
        if let override = ProcessInfo.processInfo.environment["DESK_COMPOSE_FILE"],
           fm.fileExists(atPath: override) {
            return override
        }
        if let bundled = Bundle.main.url(forResource: "docker-compose", withExtension: "yml"),
           fm.fileExists(atPath: bundled.path) {
            return bundled.path
        }
        var dir = URL(fileURLWithPath: ProcessInfo.processInfo.arguments[0]).deletingLastPathComponent()
        for _ in 0..<8 {
            let candidate = dir.appendingPathComponent("docker-compose.yml")
            if fm.fileExists(atPath: candidate.path) { return candidate.path }
            dir.deleteLastPathComponent()
        }
        return nil
    }

    nonisolated static func bundledImageTar() -> String? {
        let fm = FileManager.default
        if let override = ProcessInfo.processInfo.environment["DESK_IMAGE_TAR"],
           fm.fileExists(atPath: override) {
            return override
        }
        return Bundle.main.url(forResource: "engine-image", withExtension: "tar.gz")?.path
            ?? Bundle.main.url(forResource: "engine-image", withExtension: "tar")?.path
    }

    nonisolated static func runProcess(
        _ launchPath: String, _ args: [String], cwd: String? = nil
    ) async -> (Int32, String) {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: launchPath)
                process.arguments = args
                if let cwd { process.currentDirectoryURL = URL(fileURLWithPath: cwd) }
                var env = ProcessInfo.processInfo.environment
                let extra = "/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin"
                env["PATH"] = (env["PATH"].map { "\($0):\(extra)" }) ?? extra
                process.environment = env
                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = pipe
                do {
                    try process.run()
                } catch {
                    continuation.resume(returning: (-1, "launch failed: \(error.localizedDescription)"))
                    return
                }
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                continuation.resume(returning: (process.terminationStatus, String(data: data, encoding: .utf8) ?? ""))
            }
        }
    }
}
