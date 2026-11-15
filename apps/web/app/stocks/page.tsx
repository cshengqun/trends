import type { Metadata } from "next";
import { Explore } from "@/components/explore";

export const metadata: Metadata = { title: "股票探索" };

export default async function Stocks({ searchParams }: { searchParams: Promise<{ q?: string | string[] }> }) {
  const { q } = await searchParams;
  const query = typeof q === "string" ? q.slice(0, 40) : "";
  return <Explore key={query} initialQuery={query} />;
}
