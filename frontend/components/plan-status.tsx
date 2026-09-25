export type PlanPresentation = {
  state: "archived" | "available" | "generating" | "generation_failed";
  current_version: number | null;
  current_available: boolean;
  latest_run_status: string | null; latest_run_type: string | null;
};
const primary = {archived:"已归档", available:"已生成", generating:"生成中", generation_failed:"生成失败"};
export function PlanStatus({value,compact=false}:{value:PlanPresentation;compact?:boolean}) {
  const status=<span className={`plan-primary plan-${value.state}`} data-testid="plan-primary">{primary[value.state]}</span>;
  return <span className={`plan-status${compact ? " plan-status-compact" : ""}`} data-testid="plan-status">
    {compact ? <span className="plan-summary"><span>能力发展<span aria-hidden="true"> · </span></span>{status}</span> : status}
  </span>;
}
