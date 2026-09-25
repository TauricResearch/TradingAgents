import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import { SignupPanel } from "./SignupPanel";
import { SignInPanel } from "./SignInPanel";

export function AuthModal() {
  const { api, authModalOpen, authModalTab, setAuthModalTab, closeAuthModal } = useApp();
  const navigate = useNavigate();

  // Close and land on the Dashboard the moment a key is set — from either
  // panel succeeding, so this doesn't duplicate their submit logic.
  useEffect(() => {
    if (authModalOpen && api.apiKey) {
      closeAuthModal();
      navigate("/");
    }
  }, [api.apiKey, authModalOpen, closeAuthModal, navigate]);

  useEffect(() => {
    if (!authModalOpen) return undefined;
    function handleKey(event) {
      if (event.key === "Escape") closeAuthModal();
    }
    document.addEventListener("keydown", handleKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [authModalOpen, closeAuthModal]);

  if (!authModalOpen) return null;

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeAuthModal();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
        <button type="button" className="modal__close" onClick={closeAuthModal} aria-label="Close">
          ×
        </button>
        <h2 id="auth-modal-title" className="modal__title">
          Welcome to TradingAgents
        </h2>
        <div className="modal__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={authModalTab === "signup"}
            className={"modal__tab" + (authModalTab === "signup" ? " modal__tab--active" : "")}
            onClick={() => setAuthModalTab("signup")}
          >
            Create account
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={authModalTab === "signin"}
            className={"modal__tab" + (authModalTab === "signin" ? " modal__tab--active" : "")}
            onClick={() => setAuthModalTab("signin")}
          >
            Sign in
          </button>
        </div>
        {authModalTab === "signup" ? <SignupPanel /> : <SignInPanel />}
      </div>
    </div>
  );
}
