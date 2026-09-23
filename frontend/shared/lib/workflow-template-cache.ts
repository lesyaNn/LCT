import type { WorkflowTemplate, WorkflowTemplateStage } from './workflow-templates-repository';

export function normalizeWorkflowStageOrder(stages: WorkflowTemplateStage[]): WorkflowTemplateStage[] {
  return stages.map((stage, index) => ({ ...stage, orderIndex: index + 1 }));
}

export function moveWorkflowStage(stages: WorkflowTemplateStage[], fromIndex: number, toIndex: number): WorkflowTemplateStage[] {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= stages.length || toIndex >= stages.length) return stages;
  const next = [...stages];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return normalizeWorkflowStageOrder(next);
}

export function patchWorkflowStage(template: WorkflowTemplate | undefined, stageId: string, patch: Partial<WorkflowTemplateStage>): WorkflowTemplate | undefined {
  if (!template) return template;
  return { ...template, stages: template.stages.map((stage) => stage.id === stageId ? { ...stage, ...patch } : stage) };
}

export function getWorkflowStageOrderMoves(currentStages: WorkflowTemplateStage[], targetStages: WorkflowTemplateStage[]): Array<{ stageId: string; orderIndex: number }> {
  const working = [...currentStages].sort((left, right) => left.orderIndex - right.orderIndex);
  const moves: Array<{ stageId: string; orderIndex: number }> = [];
  targetStages.forEach((target, targetIndex) => {
    const currentIndex = working.findIndex((stage) => stage.id === target.id);
    if (currentIndex < 0 || currentIndex === targetIndex) return;
    moves.push({ stageId: target.id, orderIndex: targetIndex + 1 });
    const [moved] = working.splice(currentIndex, 1);
    working.splice(targetIndex, 0, moved);
  });
  return moves;
}
