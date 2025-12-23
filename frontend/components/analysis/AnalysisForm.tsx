/**
 * Analysis form component
 */
"use client";

import { useState, useEffect, useMemo } from "react";
import { useForm, ControllerRenderProps } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { format } from "date-fns";
import { CheckIcon } from "lucide-react";
import { getApiSettingsAsync } from "@/lib/storage";
import { getBaseUrlForModel, getApiKeyForModel } from "@/lib/api-helpers";
import Image from "next/image";
import { useLanguage } from "@/contexts/LanguageContext";

import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { DatePicker } from "@/components/ui/date-picker";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AnalysisRequest } from "@/lib/types";

const formSchema = z.object({
  ticker: z.string().min(1, "股票代碼為必填").max(10),
  analysis_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "日期格式必須為 YYYY-MM-DD"),
  analysts: z.array(z.string()).min(1, "請至少選擇一位分析師"),
  research_depth: z.number().int().min(1).max(5),
  quick_think_llm: z.string().min(1, "請選擇快速思維模型"),
  deep_think_llm: z.string().min(1, "請選擇深層思維模型"),
  embedding_model: z.string().min(1, "請選擇嵌入式模型"),

  // Market type selection: us=美股, twse=上市, tpex=上櫃/興櫃
  market_type: z.enum(["us", "twse", "tpex"]),

  // Custom model names (when "custom" is selected)
  custom_quick_think_model: z.string().optional(),
  custom_deep_think_model: z.string().optional(),

  // API Configuration (hidden from UI, populated from localStorage)
  quick_think_base_url: z
    .string()
    .url("請輸入有效的 URL")
    .optional()
    .or(z.literal("")),
  deep_think_base_url: z
    .string()
    .url("請輸入有效的 URL")
    .optional()
    .or(z.literal("")),
  quick_think_api_key: z.string().optional().or(z.literal("")),
  deep_think_api_key: z.string().optional().or(z.literal("")),
  embedding_base_url: z
    .string()
    .url("請輸入有效的 URL")
    .optional()
    .or(z.literal("")),
  embedding_api_key: z.string().optional().or(z.literal("")), // 本地模型不需要 API Key
  alpha_vantage_api_key: z.string().optional().or(z.literal("")), // 選填
  finmind_api_key: z.string().optional().or(z.literal("")), // 選填
});

interface AnalysisFormProps {
  onSubmit: (data: AnalysisRequest) => void;
  loading?: boolean;
}

// ANALYSTS is now defined inside the component using translations

export function AnalysisForm({ onSubmit, loading = false }: AnalysisFormProps) {
  const { t, locale } = useLanguage();
  
  // Define ANALYSTS using translations
  const ANALYSTS = useMemo(() => [
    { value: "market", label: t.agents.market_analyst },
    { value: "social", label: t.agents.social_analyst },
    { value: "news", label: t.agents.news_analyst },
    { value: "fundamentals", label: t.agents.fundamentals_analyst },
  ], [t]);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      ticker: "NVDA",
      analysis_date: format(new Date(), "yyyy-MM-dd"),
      analysts: ["market", "social", "news", "fundamentals"], // 預設全選
      research_depth: 3, // 預設中等層級
      market_type: "us", // 預設美股
      quick_think_llm: "gpt-5-mini",
      deep_think_llm: "gpt-5-mini",
      embedding_model: "all-MiniLM-L6-v2", // 預設使用本地開源模型
      custom_quick_think_model: "",
      custom_deep_think_model: "",
      quick_think_base_url: "https://api.openai.com/v1",
      deep_think_base_url: "https://api.openai.com/v1",
      quick_think_api_key: "",
      deep_think_api_key: "",
      embedding_base_url: "https://api.openai.com/v1",
      embedding_api_key: "",
      alpha_vantage_api_key: "",
      finmind_api_key: "",
    },
  });

  // Load API settings from localStorage and update when models change
  const quickThinkLlm = form.watch("quick_think_llm");
  const deepThinkLlm = form.watch("deep_think_llm");
  const embeddingModel = form.watch("embedding_model");
  const marketType = form.watch("market_type");
  const isQuickThinkCustom = quickThinkLlm === "custom";
  const isDeepThinkCustom = deepThinkLlm === "custom";
  const isLocalEmbedding = ["all-MiniLM-L6-v2", "all-mpnet-base-v2"].includes(embeddingModel);

  useEffect(() => {
    // Use async version to get decrypted API keys
    const loadSettings = async () => {
      const savedSettings = await getApiSettingsAsync();

      // For custom models, always use custom base URL and API key
      if (isQuickThinkCustom) {
        form.setValue(
          "quick_think_base_url",
          savedSettings.custom_base_url || ""
        );
        form.setValue(
          "quick_think_api_key",
          savedSettings.custom_api_key || ""
        );
      } else {
        form.setValue(
          "quick_think_base_url",
          getBaseUrlForModel(quickThinkLlm, savedSettings.custom_base_url)
        );
        form.setValue(
          "quick_think_api_key",
          getApiKeyForModel(quickThinkLlm, savedSettings)
        );
      }

      if (isDeepThinkCustom) {
        form.setValue(
          "deep_think_base_url",
          savedSettings.custom_base_url || ""
        );
        form.setValue("deep_think_api_key", savedSettings.custom_api_key || "");
      } else {
        form.setValue(
          "deep_think_base_url",
          getBaseUrlForModel(deepThinkLlm, savedSettings.custom_base_url)
        );
        form.setValue(
          "deep_think_api_key",
          getApiKeyForModel(deepThinkLlm, savedSettings)
        );
      }

      // 本地模型不需要設定 API Key 和 Base URL
      if (!isLocalEmbedding) {
        form.setValue(
          "embedding_base_url",
          savedSettings.custom_base_url || "https://api.openai.com/v1"
        );
        form.setValue(
          "embedding_api_key",
          savedSettings.custom_api_key || savedSettings.openai_api_key
        );
      } else {
        form.setValue("embedding_base_url", "");
        form.setValue("embedding_api_key", "");
      }
      form.setValue(
        "alpha_vantage_api_key",
        savedSettings.alpha_vantage_api_key || ""
      );
      form.setValue("finmind_api_key", savedSettings.finmind_api_key || "");
    };

    loadSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quickThinkLlm, deepThinkLlm, embeddingModel, isQuickThinkCustom, isDeepThinkCustom, isLocalEmbedding]);

  // 當市場類型改變時，更新預設股票代碼和提示
  useEffect(() => {
    const currentTicker = form.getValues("ticker");
    // 只在用戶未修改預設值時才自動切換
    const isTwStock = marketType === "twse" || marketType === "tpex";
    const isDefaultUsTicker =
      currentTicker === "NVDA" || currentTicker === "AAPL";
    const isDefaultTwTicker =
      currentTicker === "2330" ||
      currentTicker === "2317" ||
      currentTicker === "6488";

    if (isTwStock && isDefaultUsTicker) {
      form.setValue("ticker", marketType === "twse" ? "2330" : "6488");
    } else if (marketType === "us" && isDefaultTwTicker) {
      form.setValue("ticker", "NVDA");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketType]);

  // 全選/取消全選
  const toggleSelectAll = () => {
    const currentAnalysts = form.getValues("analysts");
    if (currentAnalysts.length === ANALYSTS.length) {
      form.setValue("analysts", []);
    } else {
      form.setValue(
        "analysts",
        ANALYSTS.map((a) => a.value)
      );
    }
  };

  function handleSubmit(values: z.infer<typeof formSchema>) {
    // Use custom model names if "custom" is selected
    const finalQuickThinkLlm =
      values.quick_think_llm === "custom"
        ? values.custom_quick_think_model || ""
        : values.quick_think_llm;

    const finalDeepThinkLlm =
      values.deep_think_llm === "custom"
        ? values.custom_deep_think_model || ""
        : values.deep_think_llm;

    // Validate custom model names
    if (
      values.quick_think_llm === "custom" &&
      !values.custom_quick_think_model
    ) {
      form.setError("custom_quick_think_model", {
        type: "manual",
        message: "請輸入快速思維模型的完整名稱",
      });
      return;
    }

    if (values.deep_think_llm === "custom" && !values.custom_deep_think_model) {
      form.setError("custom_deep_think_model", {
        type: "manual",
        message: "請輸入深層思維模型的完整名稱",
      });
      return;
    }

    // Validate API keys are set (they come from localStorage/settings)
    if (!values.quick_think_api_key) {
      alert("請先在右上角「設定」中設定您的 API Key。\n\n快速思維模型需要對應的 API Key 才能運作。");
      return;
    }
    
    if (!values.deep_think_api_key) {
      alert("請先在右上角「設定」中設定您的 API Key。\n\n深層思維模型需要對應的 API Key 才能運作。");
      return;
    }

    const request: AnalysisRequest = {
      ...values,
      quick_think_llm: finalQuickThinkLlm,
      deep_think_llm: finalDeepThinkLlm,
      language: locale as "en" | "zh-TW",  // Pass current UI language to backend
    };
    onSubmit(request);
  }

  return (
    <Card className="shadow-lg hover-lift animate-scale-up">
      <CardContent className="pt-6">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-6"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* 分析師選擇區塊 - 全寬 */}
              <div className="md:col-span-2 border-b pb-6">
                <div className="flex justify-between items-center mb-4">
                  <FormLabel className="text-base font-semibold">
                    {t.form.analysts}
                  </FormLabel>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={toggleSelectAll}
                  >
                    {form.watch("analysts").length === ANALYSTS.length
                      ? t.form.deselectAll
                      : t.form.selectAll}
                  </Button>
                </div>
                <FormField
                  control={form.control}
                  name="analysts"
                  render={({ field }) => (
                    <FormItem>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {ANALYSTS.map((analyst) => {
                          const isSelected = field.value?.includes(
                            analyst.value
                          );
                          return (
                            <FormItem key={analyst.value} className="space-y-0">
                              <FormControl>
                                <div
                                  onClick={() => {
                                    const newValue = isSelected
                                      ? field.value?.filter(
                                          (v: string) => v !== analyst.value
                                        )
                                      : [...(field.value ?? []), analyst.value];
                                    field.onChange(newValue);
                                  }}
                                  className={cn(
                                    "relative flex cursor-pointer flex-row items-center gap-3 rounded-lg border-2 p-4 transition-all hover:bg-accent",
                                    isSelected
                                      ? "border-primary bg-primary/5 text-primary"
                                      : "border-muted-foreground/25 bg-card text-muted-foreground"
                                  )}
                                >
                                  <div
                                    className={cn(
                                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border transition-colors",
                                      isSelected
                                        ? "border-primary bg-primary text-primary-foreground"
                                        : "border-muted-foreground"
                                    )}
                                  >
                                    {isSelected && (
                                      <CheckIcon className="h-3.5 w-3.5" />
                                    )}
                                  </div>
                                  <span className="font-medium select-none">
                                    {analyst.label}
                                  </span>
                                </div>
                              </FormControl>
                            </FormItem>
                          );
                        })}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* 第一行：市場類型、股票代碼、分析日期（3列） */}
              <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* 市場類型選擇 */}
                <FormField
                  control={form.control}
                  name="market_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.marketType}</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t.form.selectMarket} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem
                            value="us"
                            className="py-3 cursor-pointer"
                          >
                            🇺🇸 {t.form.usMarket}
                          </SelectItem>
                          <SelectItem
                            value="twse"
                            className="py-3 cursor-pointer"
                          >
                            🇹🇼 {t.form.twseMarket}
                          </SelectItem>
                          <SelectItem
                            value="tpex"
                            className="py-3 cursor-pointer"
                          >
                            🇹🇼 {t.form.tpexMarket}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>{t.form.selectMarketDesc}</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 股票代碼 */}
                <FormField
                  control={form.control}
                  name="ticker"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.ticker}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder={
                            marketType === "us"
                              ? "NVDA"
                              : marketType === "twse"
                              ? "2330"
                              : "6488"
                          }
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        {marketType === "us"
                          ? t.form.tickerDescUS
                          : marketType === "twse"
                          ? t.form.tickerDescTWSE
                          : t.form.tickerDescTPEX}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="analysis_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.analysisDate}</FormLabel>
                      <FormControl>
                        <DatePicker
                          date={field.value ? new Date(field.value) : undefined}
                          onDateChange={(date) => {
                            field.onChange(
                              date ? format(date, "yyyy-MM-dd") : ""
                            );
                          }}
                          placeholder={t.form.selectDate}
                          className="w-full"
                        />
                      </FormControl>
                      <FormDescription>{t.form.selectDate}</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* 第二行：研究深度、快速思維模型、深層思維模型、嵌入式模型（4列） */}
              <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-4 gap-6">
                <FormField
                  control={form.control}
                  name="research_depth"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.researchDepth}</FormLabel>
                      <Select
                        onValueChange={(value) =>
                          field.onChange(parseInt(value))
                        }
                        defaultValue={field.value?.toString() ?? "3"}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t.form.selectDepth} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="max-h-80">
                          <SelectItem value="1" className="py-3 cursor-pointer">
                            {t.form.depthShallowLabel}
                          </SelectItem>
                          <SelectItem value="3" className="py-3 cursor-pointer">
                            {t.form.depthMediumLabel}
                          </SelectItem>
                          <SelectItem value="5" className="py-3 cursor-pointer">
                            {t.form.depthDeepLabel}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>{t.form.selectDepth}</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="quick_think_llm"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.quickThinkModel}</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="選擇模型" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {/* OpenAI */}
                          <SelectItem value="gpt-5.2-2025-12-11">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5.2</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5.1">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5.1</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5 Mini</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5-nano">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5 Nano</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-4.1-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-4.1 Mini</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-4.1-nano">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-4.1 Nano</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="o4-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>o4-mini</span>
                            </div>
                          </SelectItem>

                          {/* Anthropic (Official model IDs) */}
                          <SelectItem value="claude-sonnet-4-5-20250929">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Sonnet 4.5</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-haiku-4-5-20251001">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Haiku 4.5</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-sonnet-4-20250514">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Sonnet 4</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-7-sonnet-20250219">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3.7 Sonnet</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-5-haiku-20241022">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3.5 Haiku</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-haiku-20240307">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3 Haiku</span>
                            </div>
                          </SelectItem>

                          {/* Google */}
                          <SelectItem value="gemini-2.5-pro">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Pro</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.5-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Flash</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.5-flash-lite">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Flash Lite</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.0-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.0 Flash</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.0-flash-lite">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.0 Flash Lite</span>
                            </div>
                          </SelectItem>

                          {/* Grok */}
                          <SelectItem value="grok-4-1-fast-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4.1 Fast Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-1-fast-non-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4.1 Fast Non Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-fast-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4 Fast Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-fast-non-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4 Fast Non Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-0709">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-3">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 3</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-3-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 3 Mini</span>
                            </div>
                          </SelectItem>

                          {/* DeepSeek */}
                          <SelectItem value="deepseek-reasoner">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/deepseek-color.svg" alt="DeepSeek" width={16} height={16} className="shrink-0" />
                              <span>DeepSeek Reasoner</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="deepseek-chat">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/deepseek-color.svg" alt="DeepSeek" width={16} height={16} className="shrink-0" />
                              <span>DeepSeek Chat</span>
                            </div>
                          </SelectItem>

                          {/* Qwen */}
                          <SelectItem value="qwen3-max">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen 3 Max</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="qwen-plus">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen Plus</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="qwen-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen Flash</span>
                            </div>
                          </SelectItem>

                          {/* Custom Model */}
                          <SelectItem value="custom">
                            {t.form.otherCustomModel}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>{t.form.quickResponseModel}</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Custom Quick Think Model Input */}
                {isQuickThinkCustom && (
                  <FormField
                    control={form.control}
                    name="custom_quick_think_model"
                    render={({ field }) => (
                      <FormItem className="md:col-span-3 animate-scale-up">
                        <FormLabel>自訂快速思維模型名稱</FormLabel>
                        <FormControl>
                          <Input placeholder="例如：deepseek-chat" {...field} />
                        </FormControl>
                        <FormDescription>
                          請輸入完整的模型名稱（此模型將使用自訂端點）
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                <FormField
                  control={form.control}
                  name="deep_think_llm"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.deepThinkModel}</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="選擇模型" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {/* OpenAI */}
                          <SelectItem value="gpt-5.2-2025-12-11">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5.2</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5.1">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5.1</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5 Mini</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-5-nano">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-5 Nano</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-4.1-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-4.1 Mini</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gpt-4.1-nano">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>GPT-4.1 Nano</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="o4-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>o4-mini</span>
                            </div>
                          </SelectItem>

                          {/* Anthropic (Official model IDs) */}
                          <SelectItem value="claude-sonnet-4-5-20250929">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Sonnet 4.5</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-haiku-4-5-20251001">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Haiku 4.5</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-sonnet-4-20250514">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude Sonnet 4</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-7-sonnet-20250219">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3.7 Sonnet</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-5-haiku-20241022">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3.5 Haiku</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="claude-3-haiku-20240307">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/claude-color.svg" alt="Claude" width={16} height={16} className="shrink-0" />
                              <span>Claude 3 Haiku</span>
                            </div>
                          </SelectItem>

                          {/* Google */}
                          <SelectItem value="gemini-2.5-pro">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Pro</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.5-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Flash</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.5-flash-lite">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.5 Flash Lite</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.0-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.0 Flash</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="gemini-2.0-flash-lite">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/gemini-color.svg" alt="Gemini" width={16} height={16} className="shrink-0" />
                              <span>Gemini 2.0 Flash Lite</span>
                            </div>
                          </SelectItem>

                          {/* Grok */}
                          <SelectItem value="grok-4-1-fast-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4.1 Fast Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-1-fast-non-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4.1 Fast Non Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-fast-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4 Fast Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-fast-non-reasoning">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4 Fast Non Reasoning</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-4-0709">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 4</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-3">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 3</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="grok-3-mini">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/grok.svg" alt="Grok" width={16} height={16} className="shrink-0" />
                              <span>Grok 3 Mini</span>
                            </div>
                          </SelectItem>

                          {/* DeepSeek */}
                          <SelectItem value="deepseek-reasoner">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/deepseek-color.svg" alt="DeepSeek" width={16} height={16} className="shrink-0" />
                              <span>DeepSeek Reasoner</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="deepseek-chat">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/deepseek-color.svg" alt="DeepSeek" width={16} height={16} className="shrink-0" />
                              <span>DeepSeek Chat</span>
                            </div>
                          </SelectItem>

                          {/* Qwen */}
                          <SelectItem value="qwen3-max">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen 3 Max</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="qwen-plus">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen Plus</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="qwen-flash">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/qwen-color.svg" alt="Qwen" width={16} height={16} className="shrink-0" />
                              <span>Qwen Flash</span>
                            </div>
                          </SelectItem>

                          {/* Custom Model */}
                          <SelectItem value="custom">
                            {t.form.otherCustomModel}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>{t.form.complexReasoningModel}</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Custom Deep Think Model Input */}
                {isDeepThinkCustom && (
                  <FormField
                    control={form.control}
                    name="custom_deep_think_model"
                    render={({ field }) => (
                      <FormItem className="md:col-span-3 animate-scale-up">
                        <FormLabel>{t.form.customDeepThinkModelName}</FormLabel>
                        <FormControl>
                          <Input placeholder="例如：deepseek-chat" {...field} />
                        </FormControl>
                        <FormDescription>
                          請輸入完整的模型名稱（此模型將使用自訂端點）
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {/* 嵌入式模型 */}
                <FormField
                  control={form.control}
                  name="embedding_model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t.form.embeddingModel}</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="選擇嵌入式模型" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {/* 本地開源模型 (不需要 API Key) */}
                          <SelectItem value="all-MiniLM-L6-v2">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/huggingface-color.svg" alt="HuggingFace" width={16} height={16} className="shrink-0" />
                              <span>all-MiniLM-L6-v2</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="all-mpnet-base-v2">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/huggingface-color.svg" alt="HuggingFace" width={16} height={16} className="shrink-0" />
                              <span>all-mpnet-base-v2</span>
                            </div>
                          </SelectItem>
                          
                          {/* OpenAI API 模型 (需要 API Key) */}
                          <SelectItem value="text-embedding-3-small">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>text-embedding-3-small</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="text-embedding-3-large">
                            <div className="flex items-center gap-2">
                              <Image src="/logos/openai.svg" alt="OpenAI" width={16} height={16} className="shrink-0" />
                              <span>text-embedding-3-large</span>
                            </div>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        {isLocalEmbedding 
                          ? t.form.localModelNoApiKey 
                          : t.form.needsOpenAiApiKey}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 hover:from-blue-600 hover:to-pink-600 dark:hover:from-blue-700 dark:hover:to-purple-700 shadow-lg hover:shadow-xl transition-all animate-heartbeat"
              disabled={loading}
              size="lg"
              style={{
                touchAction: "manipulation",
                WebkitTapHighlightColor: "transparent",
              }}
              onClick={(e) => {
                // Ensure touch events work on Safari mobile
                e.currentTarget.blur();
              }}
            >
              {loading ? t.form.analyzing : t.form.executeAnalysis}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
