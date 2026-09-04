import { FixtureDetailClient } from "./FixtureDetailClient";

export default async function FixtureDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ fixtureId: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const { fixtureId } = await params;
  const { date } = await searchParams;

  return <FixtureDetailClient fixtureId={Number(fixtureId)} initialDate={date} />;
}
