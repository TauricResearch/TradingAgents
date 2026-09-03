import { NextRequest } from "next/server";
import { getSession } from "@/lib/store";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = getSession(params.id);
  if (!session) {
    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  const encoder = new TextEncoder();
  let cancelled = false;
  let currentIndex = session.logs.length;

  const stream = new ReadableStream({
    start(controller) {
      // Send existing logs
      for (const log of session!.logs) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(log)}\n\n`)
        );
      }
      currentIndex = session!.logs.length;

      // Poll for new logs
      const interval = setInterval(() => {
        if (cancelled) {
          clearInterval(interval);
          controller.close();
          return;
        }

        const current = getSession(params.id);
        if (!current) {
          clearInterval(interval);
          controller.enqueue(encoder.encode("data: {\"done\":true}\n\n"));
          controller.close();
          return;
        }

        while (currentIndex < current.logs.length) {
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify(current.logs[currentIndex])}\n\n`)
          );
          currentIndex++;
        }

        if (current.status !== "running" && current.status !== "pending") {
          clearInterval(interval);
          controller.enqueue(encoder.encode("data: {\"done\":true}\n\n"));
          controller.close();
        }
      }, 1000);

      request.signal.addEventListener("abort", () => {
        cancelled = true;
        clearInterval(interval);
      });
    },
    cancel() {
      cancelled = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
