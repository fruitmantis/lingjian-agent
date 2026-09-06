export type PlanPresentation = {
  state: "archived" | "available" | "draft" | "restricted" | "generating" | "generation_failed";
  current_version: number | null; confirmed_version: number | null; current_is_confirmed: boolean;
  current_available: boolean; confirmed_available: boolean;
  latest_run_status: string | null; latest_run_type: string | null;
};
const primary = {archived:"已归档", available:"方案可用", draft:"草稿可用", restricted:"内容受限", generating:"生成中", generation_failed:"生成失败"};
const runLabels: Record<string,string> = {pending:"等待执行",running:"进行中",ready:"成功",partial:"部分完成",failed:"失败",interrupted:"中断"};
export function PlanStatus({value}:{value:PlanPresentation}) {
  const runError=["failed","interrupted"].includes(value.latest_run_status || "");
  return <span className="plan-status" data-testid="plan-status">
    <span className={`plan-primary plan-${value.state}`} data-testid="plan-primary">{primary[value.state]}</span>
    <span className="plan-version">{value.current_version ? `${value.current_is_confirmed ? "当前版本" : "当前草稿"} V${value.current_version}${value.current_available ? "" : "（内容受限）"}` : "尚无可用版本"}</span>
    <span className="plan-version">{value.confirmed_version ? `已确认 V${value.confirmed_version}${value.confirmed_available ? "" : "（内容受限）"}` : "尚未确认"}</span>
    {value.latest_run_status && <span className={`plan-run ${runError ? "plan-run-error" : ""}`} data-testid="plan-latest-run">最近{value.latest_run_type === "revise" ? "调整" : "生成"}{runLabels[value.latest_run_status] || "状态待确认"}</span>}
  </span>;
}
