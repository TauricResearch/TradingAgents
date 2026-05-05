/** Analyses router — wires filesystem and DB sub-routers under /api/analyses. */
import { Hono } from "hono"
import { analysesDbRouter } from "../analyses-db.ts"
import { analysesFsRouter } from "../analyses-fs.ts"

export const analysesRouter = new Hono()

analysesRouter.route("/", analysesFsRouter) // GET /, GET /:ticker/:date/*
analysesRouter.route("/", analysesDbRouter) // GET /list, GET /:id (DB id)
