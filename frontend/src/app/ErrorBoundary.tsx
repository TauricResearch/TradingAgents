import { Component, type ErrorInfo, type ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  label?: string;
}

interface State {
  error: Error | null;
}

/** Per-panel isolation: one broken widget never blanks the terminal. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // production builds minify away React's own component-stack logging;
    // without this line a crash in prod is an anonymous #185-style code
    console.error(
      `[ErrorBoundary:${this.props.label ?? "panel"}]`,
      error,
      info.componentStack,
    );
  }

  render() {
    if (this.state.error) {
      return (
        <EmptyState
          kind="error"
          title={`${this.props.label ?? "This panel"} failed to render`}
          detail={this.state.error.message}
          action={
            <Button
              size="sm"
              variant="outline"
              onClick={() => this.setState({ error: null })}
            >
              Retry
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
