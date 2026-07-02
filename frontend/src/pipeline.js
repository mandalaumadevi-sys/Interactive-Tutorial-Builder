// The execution-pipeline map (read-only live view) and the node/gate → step wiring.

export const PIPELINE = [
  { id: "ingest", label: "Ingest + image descriptions", kind: "auto" },
  { id: "divide", label: "Divide into content blocks", kind: "auto" },
  { id: "block", label: "Review block division", kind: "human" },
  { id: "content", label: "Agent 1 · Author block content", kind: "auto" },
  { id: "reviewContent", label: "Review content", kind: "human" },
  { id: "animation", label: "Agent 2 · Generate animations", kind: "auto" },
  { id: "reviewAnimation", label: "Review animations", kind: "human" },
  { id: "mcq", label: "Agent 3 · Generate MCQs", kind: "auto" },
  { id: "reviewMcq", label: "Review MCQs (accept per block)", kind: "human" },
  { id: "assessment", label: "Agent 4 · Generate assessment", kind: "auto" },
  { id: "final", label: "Review assessment", kind: "human" },
  { id: "finalReview", label: "Final review (whole tutorial)", kind: "human" },
  { id: "assemble", label: "Publish tutorial", kind: "auto" },
];

export const NODE_TO_STEP = {
  ingest: "ingest", divide: "divide", human_block_review: "block",
  content: "content", human_content_review: "reviewContent",
  animation: "animation", human_animation_review: "reviewAnimation",
  mcq: "mcq", human_mcq_review: "reviewMcq",
  assessment: "assessment", human_assessment_review: "final",
  prepare_final_review: "finalReview", human_final_review: "finalReview",
  assemble: "assemble", memory: "assemble",
};

export const STAGE_TO_STEP = {
  block: "block", content: "reviewContent", animation: "reviewAnimation",
  mcq: "reviewMcq", assessment: "final", final: "finalReview",
};

export const STEP_IDX = Object.fromEntries(PIPELINE.map((s, i) => [s.id, i]));

export const NODE_LABELS = {
  ingest: "Reading the session & describing images",
  divide: "Dividing into content blocks",
  content: "Agent 1 — writing block content",
  animation: "Agent 2 — building animations",
  mcq: "Agent 3 — writing quizzes",
  assessment: "Building the final assessment",
  prepare_final_review: "Assembling the full tutorial for final review",
  draft: "Assembling a draft",
  quality: "Checking quality",
  refine: "Refining low-scoring parts",
  assemble: "Finalizing the tutorial",
  memory: "Updating course memory",
};

// Given pipeline progress, return each step tagged with its visual state.
export function pipelineStates({ reached = -1, waiting = null, done = false }) {
  return PIPELINE.map((step, i) => {
    let state;
    if (done) state = "done";
    else if (waiting === step.id) state = "wait";
    else if (i < reached) state = "done";
    else if (i === reached) state = "active";
    else state = "pending";
    return { ...step, state };
  });
}
