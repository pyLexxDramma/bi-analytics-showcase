import { redirect } from "next/navigation";
import { AiAssistantView } from "@/components/ai-assistant-view";

export default function Page() {
  if (process.env.NEXT_PUBLIC_AI_MODE === "full") {
    redirect(
      process.env.NEXT_PUBLIC_OPENCODE_URL
        || "https://opencode.conall.ru/L3dvcmtzcGFjZQ/session",
    );
  }

  return <AiAssistantView />;
}
