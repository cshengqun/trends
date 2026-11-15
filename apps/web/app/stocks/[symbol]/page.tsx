import { Stock } from "@/components/stock";

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  return <Stock symbol={(await params).symbol.toUpperCase()} />;
}
