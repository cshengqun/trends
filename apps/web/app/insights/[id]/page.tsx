import { InsightDetail } from "@/components/insight";

export default async function InsightPage({ params }: { params: Promise<{ id: string }> }) {
  return <InsightDetail id={(await params).id} />;
}
