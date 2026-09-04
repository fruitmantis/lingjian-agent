import TaskList from "../../../components/task-list";

export default function AdminTasksPage() {
  return <main className="page"><p className="eyebrow">All Tasks</p><h1>全量任务</h1><p className="lead">查看公司内部用户发起的全部伙伴匹配任务。</p><TaskList admin /></main>;
}
