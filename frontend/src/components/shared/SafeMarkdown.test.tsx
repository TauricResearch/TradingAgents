import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafeMarkdown } from "./SafeMarkdown";

describe("SafeMarkdown", () => {
  it("renders the supported research-document Markdown subset", () => {
    render(
      <SafeMarkdown
        content={[
          "# 标题",
          "",
          "**加粗** 与 *强调* 以及 `代码`。",
          "",
          "- 第一项",
          "- 第二项",
          "",
          "| 指标 | 数值 |",
          "| --- | --- |",
          "| PE | 20 |",
          "",
          "> 重要提示",
        ].join("\n")}
      />,
    );

    expect(screen.getByRole("heading", { name: "标题" })).toBeInTheDocument();
    expect(screen.getByText("加粗").tagName).toBe("STRONG");
    expect(screen.getByText("强调").tagName).toBe("EM");
    expect(screen.getByText("代码").tagName).toBe("CODE");
    expect(screen.getByText("第一项")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("重要提示").closest("blockquote")).not.toBeNull();
  });

  it("strips raw HTML and blocks unsafe link protocols", () => {
    render(
      <SafeMarkdown
        content={'<script>window.hacked = true</script>\n\n[危险](javascript:alert(1)) [安全](https://example.com)'}
      />,
    );

    expect(screen.queryByRole("script")).not.toBeInTheDocument();
    expect(screen.queryByText(/window\.hacked/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "危险" })).not.toBeInTheDocument();
    const safeLink = screen.getByRole("link", { name: "安全" });
    expect(safeLink).toHaveAttribute("href", "https://example.com");
    expect(safeLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(safeLink).toHaveAttribute("target", "_blank");
  });
});
