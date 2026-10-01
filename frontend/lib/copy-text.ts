/** Copy on ordinary HTTP too. On failure leave visible text selected for Ctrl+C. */
export async function copyText(text: string, visible?: HTMLElement | null): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* Fall back to the synchronous copy command. */ }
  document.getElementById("banfei-manual-copy")?.remove();
  const input = document.createElement("textarea");
  input.id = "banfei-manual-copy";
  input.value = text;
  input.readOnly = true;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  let copied = false;
  try { copied = document.execCommand("copy"); } catch { /* Show a manual copy selection below. */ }
  if (copied || visible) input.remove();
  else {
    // Generated copy content may have no equivalent on the page. Keep it
    // selected and visible so Ctrl+C still works when both copy APIs fail.
    Object.assign(input.style, { opacity: "1", zIndex: "10000", bottom: "16px", left: "16px",
      width: "min(560px, calc(100vw - 32px))", height: "96px", padding: "12px",
      background: "white", color: "#222", border: "1px solid #777" });
    input.focus();
    input.select();
    input.addEventListener("blur", () => input.remove(), { once: true });
  }
  if (!copied && visible) {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(visible);
    selection?.removeAllRanges();
    selection?.addRange(range);
    visible.focus();
  }
  return copied;
}
