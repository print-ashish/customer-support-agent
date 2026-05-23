import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function normalizeContent(text) {
  return text.replace(/<br\s*\/?>/gi, "\n");
}

export default function MessageContent({ content, markdown }) {
  if (!markdown) {
    return <p>{content}</p>;
  }

  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeContent(content)}</ReactMarkdown>
    </div>
  );
}
