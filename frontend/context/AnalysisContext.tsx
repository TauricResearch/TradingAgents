"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import type { AnalysisResponse } from "@/lib/types";

interface AnalysisContextType {
  analysisResult: AnalysisResponse | null;
  setAnalysisResult: (result: AnalysisResponse | null) => void;
  taskId: string | null;
  setTaskId: (taskId: string | null) => void;
  marketType: "us" | "twse" | "tpex";
  setMarketType: (type: "us" | "twse" | "tpex") => void;
}

const AnalysisContext = createContext<AnalysisContextType | undefined>(
  undefined
);

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResponse | null>(
    null
  );
  const [taskId, setTaskId] = useState<string | null>(null);
  const [marketType, setMarketType] = useState<"us" | "twse" | "tpex">("us");

  return (
    <AnalysisContext.Provider value={{ 
      analysisResult, 
      setAnalysisResult, 
      taskId, 
      setTaskId,
      marketType,
      setMarketType,
    }}>
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysisContext() {
  const context = useContext(AnalysisContext);
  if (!context) {
    throw new Error("useAnalysisContext must be used within AnalysisProvider");
  }
  return context;
}
