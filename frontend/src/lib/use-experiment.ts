"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, type Experiment } from "@/lib/api/client";

export function useExperiment() {
  const { id } = useParams<{ id: string }>();
  const [exp, setExp] = useState<Experiment | null>(null);
  const [notFound, setNotFound] = useState(false);
  const reload = useCallback(async () => {
    const { data } = await api.GET("/api/v1/experiments/{exp_id}", { params: { path: { exp_id: id } } });
    setExp(data ?? null);
    setNotFound(!data);
  }, [id]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { id, exp, setExp, notFound, reload };
}
