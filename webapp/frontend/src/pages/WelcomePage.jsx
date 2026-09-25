import { SignupPanel } from "../components/SignupPanel";
import { SignInPanel } from "../components/SignInPanel";

export function WelcomePage() {
  return (
    <div className="welcome">
      <p className="welcome__pitch">
        A desk of LLM agents — analyst, researcher, trader, risk — debates a ticker and prints a
        BUY, SELL or HOLD call with the full case behind it.
      </p>
      <div className="welcome__panels">
        <SignupPanel />
        <SignInPanel />
      </div>
    </div>
  );
}
