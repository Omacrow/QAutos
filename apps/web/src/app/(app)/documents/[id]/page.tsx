import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { DocumentDetail } from "./document-detail";

export const metadata: Metadata = { title: "Document" };

export default function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 max-w-5xl" />}>
      <DocumentDetail params={params} />
    </Suspense>
  );
}
