/** Analyses router — wires filesystem and DB sub-routers under /api/analyses. */
import { Hono } from "hono"
import { analysesDbRouter } from "../analyses-db.tsx"
import { analysesFsRouter } from "../analyses-fs.ts"

export const analysesRouter = new Hono()

// Mount DB router FIRST — exact routes (/list, /list/html) must take priority
// over filesystem router's parameterized /:ticker/:date paths.
analysesRouter.route("/", analysesDbRouter) // GET /list, GET /list/html, GET /:id, GET /:id/card
analysesRouter.route("/", analysesFsRouter) // GET /, GET /:ticker/:date/*
