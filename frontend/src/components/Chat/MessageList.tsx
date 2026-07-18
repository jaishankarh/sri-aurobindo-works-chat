import { useEffect, useRef } from "react";
import { useChatStore } from "@/stores/useChatStore";
import { MessageBubble } from "./MessageBubble";
import { BookOpen } from "lucide-react";

export function MessageList() {
  const messages = useChatStore((state) => state.messages);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-amber-100">
          <BookOpen className="h-8 w-8 text-amber-600" />
        </div>
        <div>
          <h2 className="text-xl font-serif font-semibold text-stone-800">
            Explore the Complete Works
          </h2>
          <p className="mt-2 text-sm text-stone-500 max-w-sm">
            Ask any question about Sri Aurobindo and The Mother's philosophy,
            poetry, plays, or correspondences in English, French, or Sanskrit.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 w-full max-w-md">
          {[
            "What is Sri Aurobindo's concept of the Supermind?",
            "Explain the relationship between Sat, Chit, and Ananda",
            "Quelle est la nature du Yoga intégral?",
            "How does Savitri describe the experience of Satyavan's death?",
          ].map((suggestion) => (
            <button
              key={suggestion}
              className="rounded-lg border border-stone-200 bg-surface px-4 py-2.5 text-left text-sm text-stone-600 hover:border-amber-300 hover:bg-amber-50 transition-all"
              onClick={() => {
                // Dispatch suggestion click
                const event = new CustomEvent("rag:suggestion", {
                  detail: { query: suggestion },
                });
                window.dispatchEvent(event);
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      <div ref={bottomRef} className="h-4" />
    </div>
  );
}
