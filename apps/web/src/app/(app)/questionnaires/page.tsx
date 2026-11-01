import type { Metadata } from "next";

import { QuestionnairesView } from "./questionnaires-view";

export const metadata: Metadata = { title: "Questionnaires" };

export default function QuestionnairesPage() {
  return <QuestionnairesView />;
}
