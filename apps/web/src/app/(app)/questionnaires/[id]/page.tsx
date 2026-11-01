import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { QuestionnaireDetail } from "./questionnaire-detail";

export const metadata: Metadata = { title: "Questionnaire" };

export default function QuestionnairePage({ params }: PageProps<"/questionnaires/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 max-w-5xl" />}>
      <QuestionnaireDetail params={params} />
    </Suspense>
  );
}
