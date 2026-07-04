import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ReportViewerProps = {
  report: string | null | undefined;
};

export function ReportViewer({ report }: ReportViewerProps) {
  if (!report) {
    return <p className="text-sm text-slate-400">报告尚未生成</p>;
  }

  return (
    <article className="prose prose-invert max-w-none rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-sm leading-relaxed text-slate-200">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
    </article>
  );
}
