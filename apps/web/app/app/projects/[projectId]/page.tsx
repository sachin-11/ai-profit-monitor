import { ProjectDetail } from "@/components/project-detail";

export default async function ProjectDetailRoute({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectDetail projectId={projectId} />;
}
