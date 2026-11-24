// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The session the chat talks to, and switching it (`/new`, `/resume`): the next session is opened before
 * the current one is closed, so a switch that fails leaves the chat where it was.
 */
import type { AskOptions, Session, Turn } from "../engine/index.js";

export class SessionHost {
  constructor(private session: Session) {}

  get current(): Session {
    return this.session;
  }

  ask(question: string, options?: AskOptions): Turn {
    return this.session.ask(question, options);
  }

  /** The session `open` gives, in place of this one, which is closed once the next is up. */
  async replaceWith(open: () => Promise<Session>): Promise<Session> {
    const next = await open();
    const previous = this.session;
    this.session = next;
    await previous.close();
    return next;
  }

  close(): Promise<void> {
    return this.session.close();
  }
}
