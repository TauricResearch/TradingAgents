/**
 * F3 - Hook owning workbench config fetch + analyst input selection state.
 *
 * Owns every piece of selection state that feeds RunCreateRequestDTO and
 * guarantees the quick_think_llm / deep_think_llm pair is always valid for the
 * currently selected provider. When the provider changes, the hook auto-resets
 * quick/deep to that provider's first option (or leaves them in place when the
 * provider exposes no model options, in which case the derived validationError
 * flags the situation).
 *
 * The Controls component is a pure renderer of this hook's state.
 */
import { useEffect, useState } from "react";
import type {
  ConfigResponseDTO,
  ModelOptionDTO,
  ProviderDTO,
  ResearchDepth,
  RunCreateRequestDTO,
} from "../api/contracts";
import { getConfig } from "../api/client";

export interface UseConfigResult {
  loading: boolean;
  error: Error | null;
  config: ConfigResponseDTO | null;

  ticker: string;
  setTicker: (v: string) => void;
  analysis_date: string;
  setAnalysisDate: (v: string) => void;
  selected_analysts: string[];
  setSelectedAnalysts: (v: string[]) => void;
  toggleAnalyst: (id: string) => void;
  research_depth: ResearchDepth;
  setResearchDepth: (v: ResearchDepth) => void;
  llm_provider: string;
  setLlmProvider: (v: string) => void;
  quick_think_llm: string;
  setQuickThinkLlm: (v: string) => void;
  deep_think_llm: string;
  setDeepThinkLlm: (v: string) => void;
  output_language: string;
  setOutputLanguage: (v: string) => void;
  checkpoint_enabled: boolean;
  setCheckpointEnabled: (v: boolean) => void;

  selectedProvider: ProviderDTO | null;
  quickOptions: ModelOptionDTO[];
  deepOptions: ModelOptionDTO[];
  configured_keys: Record<string, boolean>;

  buildRequest: () => RunCreateRequestDTO | null;
  validationError: string | null;
}

const DEPTHS: ReadonlyArray<ResearchDepth> = [1, 3, 5];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function isResearchDepth(v: number): v is ResearchDepth {
  return (DEPTHS as ReadonlyArray<number>).includes(v);
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<ConfigResponseDTO | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const [ticker, setTicker] = useState<string>("");
  const [analysisDate, setAnalysisDate] = useState<string>(todayIso);
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([]);
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>(1);
  const [llmProvider, setLlmProviderState] = useState<string>("");
  const [quickThinkLlm, setQuickThinkLlm] = useState<string>("");
  const [deepThinkLlm, setDeepThinkLlm] = useState<string>("");
  const [outputLanguage, setOutputLanguage] = useState<string>("English");
  const [checkpointEnabled, setCheckpointEnabled] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((c: ConfigResponseDTO) => {
        if (cancelled) return;
        setConfig(c);
        setError(null);
        // Seed selection state from config.defaults.
        const providerId =
          c.defaults.llm_provider ?? c.providers[0]?.id ?? "";
        const provider =
          c.providers.find((p) => p.id === providerId) ?? null;
        setLlmProviderState(providerId);
        setQuickThinkLlm(
          c.defaults.quick_think_llm ?? provider?.models.quick[0]?.id ?? "",
        );
        setDeepThinkLlm(
          c.defaults.deep_think_llm ?? provider?.models.deep[0]?.id ?? "",
        );
        setOutputLanguage(c.defaults.output_language);
        setResearchDepth(
          isResearchDepth(c.defaults.research_depth)
            ? c.defaults.research_depth
            : 1,
        );
        setCheckpointEnabled(c.defaults.checkpoint_enabled);
        setSelectedAnalysts(c.analysts.map((a) => a.id));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function setLlmProvider(v: string): void {
    setLlmProviderState(v);
    const provider = config?.providers.find((p) => p.id === v) ?? null;
    if (provider === null) return;
    const firstQuick = provider.models.quick[0]?.id;
    const firstDeep = provider.models.deep[0]?.id;
    if (firstQuick !== undefined) setQuickThinkLlm(firstQuick);
    if (firstDeep !== undefined) setDeepThinkLlm(firstDeep);
    // When the new provider exposes no model options (custom-only) the stale
    // strings are left in place; the derived validationError below flags it.
  }

  function toggleAnalyst(id: string): void {
    setSelectedAnalysts((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id],
    );
  }

  const selectedProvider: ProviderDTO | null =
    config?.providers.find((p) => p.id === llmProvider) ?? null;
  const quickOptions: ModelOptionDTO[] = selectedProvider?.models.quick ?? [];
  const deepOptions: ModelOptionDTO[] = selectedProvider?.models.deep ?? [];
  const configured_keys: Record<string, boolean> =
    config?.configured_keys ?? {};

  // Derived validation: always reflects exactly why buildRequest would return
  // null. Computed each render (cheap) so it never diverges from buildRequest.
  let validationError: string | null = null;
  if (config !== null) {
    const trimmedTicker = ticker.trim();
    if (!trimmedTicker) {
      validationError = "请输入股票代码";
    } else if (selectedAnalysts.length === 0) {
      validationError = "至少选择一个分析师";
    } else {
      const provider = config.providers.find((p) => p.id === llmProvider);
      if (provider === undefined) {
        validationError = "请选择 LLM Provider";
      } else if (
        config.configured_keys[llmProvider] !== true &&
        provider.requires_api_key
      ) {
        validationError = "所选 Provider 未配置 API Key";
      } else if (quickOptions.length === 0) {
        validationError = "所选 Provider 未提供快速思考模型选项";
      } else if (deepOptions.length === 0) {
        validationError = "所选 Provider 未提供深度思考模型选项";
      } else if (!quickThinkLlm) {
        validationError = "请选择快速思考模型";
      } else if (!deepThinkLlm) {
        validationError = "请选择深度思考模型";
      }
    }
  }

  function buildRequest(): RunCreateRequestDTO | null {
    if (config === null || validationError !== null) return null;
    const orderedAnalysts = config.analysts
      .map((a) => a.id)
      .filter((id) => selectedAnalysts.includes(id));
    return {
      ticker: ticker.trim(),
      analysis_date: analysisDate,
      selected_analysts: orderedAnalysts,
      research_depth: researchDepth,
      llm_provider: llmProvider,
      quick_think_llm: quickThinkLlm,
      deep_think_llm: deepThinkLlm,
      output_language: outputLanguage,
      checkpoint_enabled: checkpointEnabled,
      asset_type: null,
    };
  }

  return {
    loading: config === null && error === null,
    error,
    config,
    ticker,
    setTicker,
    analysis_date: analysisDate,
    setAnalysisDate,
    selected_analysts: selectedAnalysts,
    setSelectedAnalysts,
    toggleAnalyst,
    research_depth: researchDepth,
    setResearchDepth,
    llm_provider: llmProvider,
    setLlmProvider,
    quick_think_llm: quickThinkLlm,
    setQuickThinkLlm,
    deep_think_llm: deepThinkLlm,
    setDeepThinkLlm,
    output_language: outputLanguage,
    setOutputLanguage,
    checkpoint_enabled: checkpointEnabled,
    setCheckpointEnabled,
    selectedProvider,
    quickOptions,
    deepOptions,
    configured_keys,
    buildRequest,
    validationError,
  };
}