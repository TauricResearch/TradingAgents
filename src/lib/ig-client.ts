/**
 * Thin IG API client using native fetch.
 *
 * No external dependencies. Works with Bun and Node.js v22+.
 * Handles v2 auth (CST/XST tokens), timeouts, and IG-specific quirks.
 *
 * Usage:
 *   const client = new IGClient({
 *     apiKey: process.env.IG_DEMO_API_KEY,
 *     username: process.env.IG_DEMO_USERNAME,
 *     password: process.env.IG_DEMO_PASSWORD,
 *     baseUrl: "https://demo-api.ig.com/gateway/deal",
 *   });
 *   await client.login();
 *   const accounts = await client.getAccounts();
 *   const ref = await client.createPosition({ epic: "...", direction: "BUY", size: 1 });
 */

export interface IGClientConfig {
  apiKey: string
  username: string
  password: string
  baseUrl: string
  accountId?: string
}

export interface IGSession {
  accountType: string
  clientId: string
  currentAccountId: string
  dealingEnabled: boolean
  hasActiveDemoAccounts: boolean
  hasActiveLiveAccounts: boolean
  lightstreamerEndpoint: string
}

export interface IGAccount {
  accountId: string
  accountName: string
  accountType: "CFD" | "PHYSICAL" | "SPREADBET"
  balance: { available: number; balance: number; deposit: number; profitLoss: number }
  canTransferFrom: boolean
  canTransferTo: boolean
  currency: string
  preferred: boolean
  status: "DISABLED" | "ENABLED" | "SUSPENDED_FROM_DEALING"
}

export interface IGMarket {
  epic: string
  instrumentName: string
  instrumentType: string
  expiry: string
  bid: number | null
  offer: number | null
  high: number
  low: number
  updateTime: string
}

export interface IGPrice {
  snapshotTime: string
  openPrice: { bid?: number; ask?: number; lastTraded?: number }
  closePrice: { bid?: number; ask?: number; lastTraded?: number }
  highPrice: { bid?: number; ask?: number; lastTraded?: number }
  lowPrice: { bid?: number; ask?: number; lastTraded?: number }
  lastTradedVolume: number
}

export interface IGPosition {
  contractSize: number
  createdDate: string
  currency: string
  dealId: string
  dealReference: string
  direction: "BUY" | "SELL"
  level: number
  limitLevel?: number
  size: number
  stopLevel?: number
  trailingStep?: number
  trailingStopDistance?: number
}

export interface IGDealReference {
  dealReference: string
}

export interface IGDealConfirmation {
  dealId: string
  dealReference: string
  dealStatus: "ACCEPTED" | "REJECTED"
  direction: "BUY" | "SELL"
  epic: string
  level: number
  size: number
  profit: number | null
  currency: string
}

const DEFAULT_TIMEOUT = 15000

export class IGClient {
  private config: IGClientConfig
  private cst: string | null = null
  private xst: string | null = null

  constructor(config: IGClientConfig) {
    this.config = config
  }

  get isLoggedIn(): boolean {
    return this.cst !== null && this.xst !== null
  }

  setAccountId(accountId: string): void {
    this.config.accountId = accountId
  }

  // ── Internal fetch with auth and timeout ────────────────────────────────────

  private async fetch<T>(
    path: string,
    options: RequestInit = {},
    timeoutMs = DEFAULT_TIMEOUT,
  ): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)

    const headers: Record<string, string> = {
      "X-IG-API-KEY": this.config.apiKey,
      "Content-Type": "application/json",
      Accept: "application/json; charset=UTF-8",
      Version: "2",
      ...(this.cst ? { CST: this.cst } : {}),
      ...(this.xst ? { "X-SECURITY-TOKEN": this.xst } : {}),
      ...(this.config.accountId ? { "IG-ACCOUNT-ID": this.config.accountId } : {}),
      ...((options.headers as Record<string, string>) || {}),
    }

    try {
      const res = await fetch(`${this.config.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        headers,
      })
      clearTimeout(timer)

      // Update tokens from response
      const newCst = res.headers.get("CST")
      const newXst = res.headers.get("X-SECURITY-TOKEN")
      if (newCst) this.cst = newCst
      if (newXst) this.xst = newXst

      if (!res.ok) {
        const text = await res.text()
        throw new Error(`IG API ${res.status}: ${text.slice(0, 200)}`)
      }

      return (await res.json()) as T
    } catch (e) {
      clearTimeout(timer)
      throw e
    }
  }

  // ── Auth ──────────────────────────────────────────────────────────────────

  async login(): Promise<IGSession> {
    const body = await this.fetch<IGSession>(
      "/session",
      {
        method: "POST",
        body: JSON.stringify({
          identifier: this.config.username,
          password: this.config.password,
        }),
      },
      10000,
    )
    return body
  }

  // ── Account ───────────────────────────────────────────────────────────────

  async getAccounts(): Promise<{ accounts: IGAccount[] }> {
    // /accounts requires Version: 1 (Version: 2 returns 404)
    return this.fetch<{ accounts: IGAccount[] }>("/accounts", { headers: { Version: "1" } }, 10000)
  }

  // ── Market ────────────────────────────────────────────────────────────────

  async searchMarkets(query: string): Promise<{ markets: IGMarket[] }> {
    const encoded = encodeURIComponent(query)
    // searchMarkets requires Version: 1 (v2/v3 return 500/404)
    return this.fetch<{ markets: IGMarket[] }>(
      `/markets?searchTerm=${encoded}`,
      { headers: { Version: "1" } },
      10000,
    )
  }

  async getPrices(epic: string, resolution: string, count: number): Promise<{ prices: IGPrice[] }> {
    const encoded = encodeURIComponent(epic)
    // getPrices requires Version: 3 (v1/v2 return 404)
    return this.fetch<{ prices: IGPrice[] }>(
      `/prices/${encoded}?resolution=${resolution}&max=${count}`,
      { headers: { Version: "3" } },
      10000,
    )
  }

  // ── Dealing ───────────────────────────────────────────────────────────────

  async createPosition(params: {
    epic: string
    direction: "BUY" | "SELL"
    size: number
    expiry?: string
    orderType?: "MARKET" | "LIMIT"
    currencyCode?: string
    forceOpen?: boolean
    guaranteedStop?: boolean
    stopDistance?: number
    limitDistance?: number
  }): Promise<IGDealReference> {
    return this.fetch<IGDealReference>(
      "/positions/otc",
      {
        method: "POST",
        body: JSON.stringify({
          epic: params.epic,
          expiry: params.expiry ?? "DFB",
          direction: params.direction,
          size: params.size,
          orderType: params.orderType ?? "MARKET",
          currencyCode: params.currencyCode ?? "GBP",
          forceOpen: params.forceOpen ?? true,
          guaranteedStop: params.guaranteedStop ?? false,
          timeInForce: "EXECUTE_AND_ELIMINATE",
          ...(params.stopDistance ? { stopDistance: params.stopDistance } : {}),
          ...(params.limitDistance ? { limitDistance: params.limitDistance } : {}),
        }),
      },
      20000,
    )
  }

  async closePosition(params: {
    dealId: string
    direction: "BUY" | "SELL"
    size: number
    epic: string
    expiry?: string
    orderType?: "MARKET" | "LIMIT"
    currencyCode?: string
  }): Promise<IGDealReference> {
    return this.fetch<IGDealReference>(
      "/positions/otc",
      {
        method: "POST",
        body: JSON.stringify({
          dealId: params.dealId,
          direction: params.direction,
          size: params.size,
          epic: params.epic,
          expiry: params.expiry ?? "-",
          orderType: params.orderType ?? "MARKET",
          timeInForce: "EXECUTE_AND_ELIMINATE",
          currencyCode: params.currencyCode ?? "GBP",
          guaranteedStop: false,
          forceOpen: false,
        }),
      },
      20000,
    )
  }

  async getPositions(): Promise<{ positions: Array<{ market: IGMarket; position: IGPosition }> }> {
    return this.fetch<{ positions: Array<{ market: IGMarket; position: IGPosition }> }>(
      "/positions",
      {},
      10000,
    )
  }

  async confirmTrade(dealReference: string): Promise<IGDealConfirmation> {
    // /confirms requires Version: 1 (v2/v3 return 500)
    return this.fetch<IGDealConfirmation>(
      `/confirms/${dealReference}`,
      { headers: { Version: "1" } },
      10000,
    )
  }
}
