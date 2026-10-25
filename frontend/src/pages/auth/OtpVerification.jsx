import { useEffect, useRef, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AuthPageShell from "../../features/auth/AuthPageShell.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

const OTP_LENGTH = 6;
const RESEND_SECONDS = 30;

export default function OtpVerification() {
  const { pendingEmail, verifyOtp, resendOtp } = useAuth();
  const [params] = useSearchParams();
  const email = pendingEmail || params.get("email") || "";
  const navigate = useNavigate();
  const [digits, setDigits] = useState(Array(OTP_LENGTH).fill(""));
  const [secondsLeft, setSecondsLeft] = useState(RESEND_SECONDS);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [resendStatus, setResendStatus] = useState("idle");
  const inputRefs = useRef([]);

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const timer = window.setTimeout(() => setSecondsLeft((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [secondsLeft]);

  function setDigit(index, value) {
    const digit = value.replace(/\D/g, "").slice(-1);
    setDigits((current) => current.map((entry, position) => position === index ? digit : entry));
    setError("");
    if (digit && index < OTP_LENGTH - 1) inputRefs.current[index + 1]?.focus();
  }

  function pasteCode(event) {
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, OTP_LENGTH);
    if (!pasted) return;
    event.preventDefault();
    setDigits(Array.from({ length: OTP_LENGTH }, (_, index) => pasted[index] ?? ""));
    inputRefs.current[Math.min(pasted.length, OTP_LENGTH) - 1]?.focus();
  }

  async function submit(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      await verifyOtp(email, digits.join(""));
      navigate(`/email-verified?email=${encodeURIComponent(email)}`, { replace: true });
    } catch (failure) {
      setStatus("error");
      setError(failure instanceof Error ? failure.message : "We couldn’t verify that code.");
    }
  }

  async function resend() {
    setResendStatus("loading");
    setError("");
    try {
      await resendOtp(email);
      setDigits(Array(OTP_LENGTH).fill(""));
      setSecondsLeft(RESEND_SECONDS);
      setResendStatus("success");
      inputRefs.current[0]?.focus();
    } catch (failure) {
      setResendStatus("error");
      setError(failure instanceof Error ? failure.message : "We couldn’t send another verification code.");
    }
  }

  return (
    <AuthPageShell eyebrow="One last check" title="Verify your email." description={email ? `Enter the six-digit code sent to ${email}.` : "Enter the six-digit code sent to your email."}>
      <form className="auth-form" onSubmit={submit}>
        <div className="otp-input-group" role="group" aria-label="Six-digit verification code">
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(element) => { inputRefs.current[index] = element; }}
              aria-label={`Verification digit ${index + 1}`}
              autoComplete={index === 0 ? "one-time-code" : "off"}
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={1}
              value={digit}
              onChange={(event) => setDigit(index, event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Backspace" && !digit && index > 0) inputRefs.current[index - 1]?.focus();
                if (event.key === "ArrowLeft" && index > 0) inputRefs.current[index - 1]?.focus();
                if (event.key === "ArrowRight" && index < OTP_LENGTH - 1) inputRefs.current[index + 1]?.focus();
              }}
              onPaste={pasteCode}
            />
          ))}
        </div>
        {error ? <p className="auth-message auth-message-error" role="alert">{error}</p> : null}
        {resendStatus === "success" ? <p className="auth-message auth-message-success" role="status">If your account needs verification, a new code has been sent.</p> : null}
        <button className="button button-dark auth-submit" type="submit" disabled={status === "loading" || digits.join("").length !== OTP_LENGTH}>
          {status === "loading" ? <><span className="loading-spinner" /> Verifying…</> : <>Verify code <ArrowRight size={15} /></>}
        </button>
      </form>
      <div className="otp-resend">
        <span>{secondsLeft > 0 ? `Resend available in 0:${String(secondsLeft).padStart(2, "0")}` : "Didn’t receive a code?"}</span>
        <button type="button" disabled={secondsLeft > 0 || resendStatus === "loading"} onClick={resend}>
          <RefreshCw size={13} /> {resendStatus === "loading" ? "Preparing…" : "Resend code"}
        </button>
      </div>
      <p className="auth-switch"><Link to="/register">Back to registration</Link></p>
    </AuthPageShell>
  );
}
