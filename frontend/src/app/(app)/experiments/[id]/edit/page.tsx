"use client";

import Link from "next/link";

import { ExperimentWizard } from "@/components/experiment-wizard";
import { Alert } from "@/components/ui/alert";
import { useExperiment } from "@/lib/use-experiment";

export default function EditExperimentPage() {
  const { id, exp, notFound } = useExperiment();
  if (notFound) return <Alert>Эксперимент не найден.</Alert>;
  if (!exp) return <p className="text-muted-foreground">Загрузка…</p>;
  if (exp.status !== "draft")
    return (
      <Alert>
        Протокол зарегистрирован, менять его нельзя. <Link href={`/experiments/${id}`} className="underline">Открыть карточку</Link>
      </Alert>
    );
  return <ExperimentWizard initial={exp} />;
}
