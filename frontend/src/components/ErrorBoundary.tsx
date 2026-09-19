import { Component } from "react";
import type { ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** Last-resort boundary (P1): one crashing widget must not kill the whole CRM. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="page" role="alert">
          <div className="card">
            <h2>Что-то пошло не так</h2>
            <p className="muted">Попробуйте обновить страницу. Детали — в консоли браузера.</p>
            <p className="err">{this.state.error.message}</p>
            <button className="btn primary" onClick={() => window.location.reload()}>
              Обновить
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
