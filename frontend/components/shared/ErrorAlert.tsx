/**
 * Error Alert Component
 * Displays user-friendly error messages with special handling for rate limits
 */
"use client";

import { AlertCircle, Clock, TrendingUp } from "lucide-react";
import { Card } from "@/components/ui/card";

interface ErrorAlertProps {
  error: string | {
    error: string;
    error_type?: string;
    retry_after?: number;
    quota_limit?: number;
  };
}

export function ErrorAlert({ error }: ErrorAlertProps) {
  // Parse error data
  const isRateLimit = typeof error === "object" && error.error_type === "rate_limit";
  const errorMessage = typeof error === "string" ? error : error.error;
  const retryAfter = typeof error === "object" ? error.retry_after : null;
  const quotaLimit = typeof error === "object" ? error.quota_limit : null;

  // Calculate retry time display
  const getRetryTimeDisplay = (seconds: number | null) => {
    if (!seconds) return null;
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes} 分 ${remainingSeconds} 秒`;
    }
    return `${remainingSeconds} 秒`;
  };

  return (
    <Card className={`p-6 border-2 ${
      isRateLimit 
        ? "bg-orange-50 dark:bg-orange-900/20 border-orange-300 dark:border-orange-700" 
        : "bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700"
    }`}>
      <div className="flex items-start gap-4">
        <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
          isRateLimit 
            ? "bg-orange-100 dark:bg-orange-800" 
            : "bg-red-100 dark:bg-red-800"
        }`}>
          {isRateLimit ? (
            <Clock className="w-5 h-5 text-orange-600 dark:text-orange-400" />
          ) : (
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
          )}
        </div>
        
        <div className="flex-1">
          <h3 className={`font-semibold text-lg mb-2 ${
            isRateLimit 
              ? "text-orange-900 dark:text-orange-200" 
              : "text-red-900 dark:text-red-200"
          }`}>
            {isRateLimit ? "API 請求額度已達上限" : "錯誤"}
          </h3>
          
          <p className={`mb-4 ${
            isRateLimit 
              ? "text-orange-800 dark:text-orange-300" 
              : "text-red-800 dark:text-red-300"
          }`}>
            {errorMessage}
          </p>

          {isRateLimit && (
            <div className="space-y-3 mt-4">
              {/* Retry Information */}
              {retryAfter && (
                <div className="flex items-start gap-2 bg-white/50 dark:bg-gray-900/50 p-3 rounded-lg">
                  <Clock className="w-4 h-4 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      建議等待時間
                    </p>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      請在 <span className="font-bold text-orange-600 dark:text-orange-400">
                        {getRetryTimeDisplay(retryAfter)}
                      </span> 後重試
                    </p>
                  </div>
                </div>
              )}

              {/* Quota Information */}
              {quotaLimit && (
                <div className="flex items-start gap-2 bg-white/50 dark:bg-gray-900/50 p-3 rounded-lg">
                  <TrendingUp className="w-4 h-4 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      每日額度限制
                    </p>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      當前計劃：每日 {quotaLimit} 次請求
                    </p>
                  </div>
                </div>
              )}

              {/* Solutions */}
              <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 p-4 rounded-lg mt-4">
                <p className="text-sm font-semibold text-blue-900 dark:text-blue-200 mb-2">
                  💡 解決方案：
                </p>
                <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-1.5 list-disc list-inside">
                  <li>等待額度重置（通常為每日重置）</li>
                  <li>升級至付費方案以獲得更高額度</li>
                  <li>減少分析師數量或研究深度以降低 API 呼叫次數</li>
                  <li>使用不同的 API 金鑰（如果有多個帳戶）</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
