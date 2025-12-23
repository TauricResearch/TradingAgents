/**
 * API Settings Dialog Component
 */
"use client";

import { useState, useEffect } from "react";
import { Settings, Cloud, CloudOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useLanguage } from "@/contexts/LanguageContext";

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
import { useAuth } from "@/contexts/auth-context";
import { getCloudSettings, saveCloudSettings, isCloudSyncEnabled } from "@/lib/user-api";

const formSchema = z.object({
  // All API keys are optional - users only need the ones for their selected models
  openai_api_key: z.string().optional().or(z.literal("")),
  
  // Stock market data APIs
  alpha_vantage_api_key: z.string().optional().or(z.literal("")),  // 美股基本面資料
  finmind_api_key: z.string().optional().or(z.literal("")),  // 台灣股市資料
  
  // LLM Providers
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
  const [syncStatus, setSyncStatus] = useState<"local" | "cloud" | "syncing">("local");
  const { isAuthenticated } = useAuth();
  const { t } = useLanguage();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: DEFAULT_API_SETTINGS,
  });

  // Load and decrypt settings when dialog opens
  useEffect(() => {
    if (open) {
      setLoading(true);
      setSaveSuccess(false);
      
      const loadSettings = async () => {
        try {
          // First try to migrate legacy settings
          await migrateToEncrypted();
          
          // If authenticated, try to load from cloud first
          if (isAuthenticated && isCloudSyncEnabled()) {
            setSyncStatus("syncing");
            const cloudSettings = await getCloudSettings();
            if (cloudSettings) {
              form.reset(cloudSettings);
              setSyncStatus("cloud");
              return;
            }
          }
          
          // Fall back to local storage
          const localSettings = await getApiSettingsAsync();
          form.reset(localSettings);
          setSyncStatus(isAuthenticated ? "cloud" : "local");
        } catch (error) {
          console.error("Failed to load settings:", error);
          setSyncStatus("local");
        } finally {
          setLoading(false);
        }
      };
      
      loadSettings();
    }
  }, [open, form, isAuthenticated]);

  const onSubmit = async (values: FormValues) => {
    setLoading(true);
    try {
      // Encrypt and save settings locally
      await saveApiSettingsAsync(values as ApiSettings);
      
      // If authenticated, also save to cloud
      if (isAuthenticated && isCloudSyncEnabled()) {
        setSyncStatus("syncing");
        const cloudSaved = await saveCloudSettings(values as ApiSettings);
        setSyncStatus(cloudSaved ? "cloud" : "local");
      }
      
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
          title={t.settings.title}
        >
          <Settings className="h-5 w-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t.settings.apiConfiguration}</DialogTitle>
          <DialogDescription>
            {t.settings.description}
            <span className="block mt-1 text-xs text-green-600 dark:text-green-400">
              {t.settings.encryptionEnabled}
            </span>
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-blue-800 dark:text-blue-300 text-sm">
                {t.settings.onlyFillNeeded}
              </div>
            </div>

            {/* Stock Market Data APIs Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                {t.settings.stockMarketApis}
              </h3>

              {/* FinMind API Key - Taiwan Stocks */}
              <FormField
                control={form.control}
                name="finmind_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t.settings.finmindToken}</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder={t.settings.finmindPlaceholder}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t.settings.finmindDesc}
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
                    <FormLabel>{t.settings.alphaVantageKey}</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder={t.settings.alphaVantagePlaceholder}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t.settings.alphaVantageDesc}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* LLM Providers Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                {t.settings.llmProviders}
              </h3>

              {/* OpenAI API Key */}
              <FormField
                control={form.control}
                name="openai_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>OpenAI API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>
                      {t.settings.openaiDesc}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="anthropic_api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Anthropic API Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="sk-..." {...field} />
                    </FormControl>
                    <FormDescription>{t.settings.anthropicDesc}</FormDescription>
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
                    <FormDescription>{t.settings.googleDesc}</FormDescription>
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
                    <FormDescription>{t.settings.grokDesc}</FormDescription>
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
                    <FormDescription>{t.settings.deepseekDesc}</FormDescription>
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
                    <FormDescription>{t.settings.qwenDesc}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Custom Endpoint Section */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-lg font-semibold text-muted-foreground">
                {t.settings.customEndpoint}
              </h3>

              {/* Custom Base URL */}
              <FormField
                control={form.control}
                name="custom_base_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t.settings.customBaseUrl}</FormLabel>
                    <FormControl>
                      <Input
                        type="text"
                        placeholder="https://your-custom-endpoint.com/v1"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t.settings.customBaseUrlDesc}
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
                    <FormLabel>{t.settings.customApiKey}</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder={t.settings.customApiKeyPlaceholder}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t.settings.customApiKeyDesc}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {saveSuccess && (
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 text-green-800 dark:text-green-300 text-sm">
                {t.settings.settingsSaved}
              </div>
            )}

            <div className="flex gap-2 pt-4">
              <Button type="submit" className="flex-1" disabled={loading}>
                {loading ? t.settings.processing : t.settings.saveSettings}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleClear}
                className="flex-1"
              >
                {t.settings.clearSettings}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
