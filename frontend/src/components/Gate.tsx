import { useState } from "react";
import { Field, Problem } from "./bits";

/**
 * The way in.
 *
 * The platform authenticates one way — an API key it issued — so this screen
 * asks for exactly that and explains where one comes from. It is the whole of
 * the first impression: the ground, the mark, and a prompt.
 */
export function Gate(props: {
  onSubmit: (key: string) => void;
  pending: boolean;
  problem: string | null;
}) {
  const [key, setKey] = useState("");

  return (
    <div className="dp-gate">
      <div className="dp-gate-panel">
        <div className="dp-gate-mark">
          <img src="/mark.svg" alt="" width="30" height="30" />
          <span className="dp-gate-wordmark">dataplatform console</span>
        </div>

        <div className="vg-modal" style={{ width: "auto", maxWidth: "none" }}>
          <div className="vg-modal-head">
            <span className="vg-modal-kind">auth</span>
            <span className="vg-modal-title">Sign in with a key</span>
          </div>
          <div className="vg-modal-body">
            <form
              className="dp-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (key.trim()) props.onSubmit(key.trim());
              }}
            >
              <Field
                label="api key"
                htmlFor="dp-key"
                gloss="Every request carries this key, and the policy decides what it may do from the roles it carries. Keys are shown once, when they are issued."
              >
                <input
                  id="dp-key"
                  className="vg-input is-lg"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="paste the key you were issued…"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                />
              </Field>

              {props.problem && <Problem>{props.problem}</Problem>}

              <div className="dp-form-actions">
                <span className="vg-spacer" />
                <button
                  type="submit"
                  className="vg-btn is-primary"
                  disabled={props.pending || key.trim() === ""}
                >
                  {props.pending ? "checking…" : "sign in"}
                </button>
              </div>
            </form>
          </div>
        </div>

        <div className="vg-note" style={{ marginTop: 14 }}>
          Running the compose stack locally? The bootstrap administrator's key is
          <code className="dp-inline-code"> BOOTSTRAP_API_KEY</code>, by default
          <code className="dp-inline-code"> dpk_local_docker_compose_development_key</code>.
        </div>
      </div>
    </div>
  );
}
