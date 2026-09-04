import TaskList from "../../components/task-list";

export default function TasksPage() {
  return <main className="page"><p className="eyebrow">My Tasks</p><h1>我的任务</h1><p className="lead">查看和管理由你发起的伙伴匹配任务。</p><TaskList /></main>;
}
