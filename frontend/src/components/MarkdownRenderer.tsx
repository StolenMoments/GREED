import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  markdown: string;
}

function MarkdownRenderer({ markdown }: MarkdownRendererProps) {
  return (
    <div className="max-w-none text-sm leading-6 text-slate-300">
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h1 className="mt-5 text-2xl font-semibold text-slate-50">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-5 text-xl font-semibold text-slate-50">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-5 text-base font-semibold text-slate-50">
              {children}
            </h3>
          ),
          p: ({ children }) => <p className="mt-3">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-amber-100">{children}</strong>
          ),
          ul: ({ children }) => (
            <ul className="mt-3 list-disc space-y-1 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mt-3 list-decimal space-y-1 pl-5">{children}</ol>
          ),
          table: ({ children }) => (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full border-collapse text-left">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-slate-800 px-3 py-2 text-slate-300">
              {children}
            </td>
          ),
        }}
        remarkPlugins={[remarkGfm]}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownRenderer;
