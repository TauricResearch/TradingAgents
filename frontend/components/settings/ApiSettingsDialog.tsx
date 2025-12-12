/**
 * API Settings Dialog Component
 */
"use client";

import { useState, useEffect } from "react";
import { Settings } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
import {
  getApiSettingsAsync,
  saveApiSettingsAsync,
  clearApiSettings,
  migrateToEncrypted,
  type ApiSettings,
  DEFAULT_API_SETTINGS,
} from "@/lib/storage";

const formSchema = z.object({
  // Required
  openai_api_key: z.string().min(1, "OpenAI API Key 為必填"),
  
  // Optional
  alpha_vantage_api_key: z.string().optional().or(z.literal("")),  // 美股基本面資料
  finmind_api_key: z.string().optional().or(z.literal("")),  // 台灣股市資料
  anthropic_api_key: z.string().optional().or(z.literal("")),
  google_api_key: z.string().optional().or(z.literal("")),
  grok_api_key: z.string().optional().or(z.literal("")),
  deepseek_api_key: z.string().optional().or(z.literal("")),
  qwen_api_key: z.string().optional().or(z.literal("")),
  
  // Custom endpoint
  custom_base_url: z.string().optional().or(z.literal("")),
  custom_api_key: z.string().optional().or(z.literal("")),
});

type FormValues = z.infer<typeof formSchema>;

export function ApiSettingsDialog() {
  const [open, setOpen] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: DEFAULT_API_SETTINGS,
  });

  // Load and decrypt settings when dialog opens
  useEffect(() => {
    if (open) {
      setLoading(true);
      setSaveSuccess(false);
      
      // First try to migrate legacy settings
      migrateToEncrypted().then(() => {
        // Then load decrypted settings
        return getApiSettingsAsync();
      }).then((settings) => {
        form.reset(settings);
      }).catch((error) => {
        console.error("Failed to load settings:", error);
      }).finally(() => {
        setLoading(false);
      });
    }
  }, [open, form]);

  const onSubmit = async (values: FormValues) => {
    setLoading(true);
    try {
      // Encrypt and save settings
      await saveApiSettingsAsync(values as ApiSettings);
      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        setOpen(false);
      }, 1500);
    } catch (error) {
      console.error("Failed to save settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    clearApiSettings();
    form.reset(DEFAULT_API_SETTINGS);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {/* @ts-ignore - React 19 type compatibility issue with Radix UI */}
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/20"
          title="API 設定"
        >
          <Settings className="h-5 w-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>API 配置</DialogTitle>
          <DialogDescription>
            設定您的 API 金鑰。這些資訊會以加密形式儲存在瀏覽器中。
            <span className="block mt-1 text-xs text-green-600 dark:text-green-400">
              🔒 已啟用 AES-256-GCM 加密保護
            </span>
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Required Section */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-primary">必填項目</h3>
              
              {/* OpenAI API Key */}
              <FormField
                control={form.control}
                name="openai_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>OpenAI API Key *</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>
                      用於 OpenAI 模型（GPT-4, GPT-5, o4 等）
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Stock Market Data APIs Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                股市資料 API（依分析市場選擇填寫）
              </h3>

              {/* FinMind API Key - Taiwan Stocks */}
              <FormField
                control={form.control}
                name="finmind_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>FinMind API Token（台股）</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="輸入 FinMind Token"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      用於獲取台灣股市資料（在 finmindtrade.com 註冊取得）
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Alpha Vantage API Key - US Stocks */}
              <FormField
                control={form.control}
                name="alpha_vantage_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Alpha Vantage API Key（美股）</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="輸入 Alpha Vantage API Key"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      用於獲取美股基本面數據（分析美股時建議填寫）
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Optional LLM Providers Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                選填項目（其他 LLM 供應商）
              </h3>

              {/* Anthropic API Key */}
              <FormField
                control={form.control}
                name="anthropic_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Anthropic API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>用於 Claude 模型</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Google API Key */}
              <FormField
                control={form.control}
                name="google_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Google API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="..." {...field} />
                    </FormControl>
                    <FormDescription>用於 Gemini 模型</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Grok API Key */}
              <FormField
                control={form.control}
                name="grok_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Grok (xAI) API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="xai-..." {...field} />
                    </FormControl>
                    <FormDescription>用於 Grok 模型</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* DeepSeek API Key */}
              <FormField
                control={form.control}
                name="deepseek_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>DeepSeek API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>用於 DeepSeek 模型</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Qwen API Key */}
              <FormField
                control={form.control}
                name="qwen_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Qwen (Alibaba) API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>用於 Qwen 模型</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Custom Endpoint Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                自訂端點（進階選項）
              </h3>

              {/* Custom Base URL */}
              <FormField
                control={form.control}
                name="custom_base_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>自訂 Base URL</FormLabel>
                    <FormControl>
                      <Input
                        type="text"
                        placeholder="https://your-custom-endpoint.com/v1"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      若設定此項，將覆蓋所有模型的預設端點
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Custom API Key */}
              <FormField
                control={form.control}
                name="custom_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>自訂端點 API Key</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="輸入自訂端點的 API Key"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      配合自訂 Base URL 使用的 API Key
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {saveSuccess && (
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 text-green-800 dark:text-green-300 text-sm">
                ✓ 設定已成功儲存
              </div>
            )}

            <div className="flex gap-2 pt-4">
              <Button type="submit" className="flex-1" disabled={loading}>
                {loading ? "處理中..." : "儲存設定"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleClear}
                className="flex-1"
              >
                清除設定
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
