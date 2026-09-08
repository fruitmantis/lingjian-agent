import TaskList from "../../components/task-list";

export default function TasksPage() {
  return <main className="page"><h1>我的任务</h1><p className="lead">查看和管理由你发起的任务，按任务类型筛选。</p><TaskList /></main>;
}
