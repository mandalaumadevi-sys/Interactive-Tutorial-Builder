# 🎤 Tuti — Presentation Script

**Total time:** ~8–10 minutes · 11 slides
**How to use:** These are talking points, not lines to memorize. Speak them in your own words. Short sentences, small pauses. Advance the slide when you see **➡️ NEXT**.

**Quick delivery tips**
- Smile on the first slide. Look at people, not the screen.
- Pause for 1 second after your hook.
- Speak slower than feels natural — it always sounds better.
- On the flowchart slide, point at the screen as you walk through it.

---

## SLIDE 1 — Title: "Tuti" 🤖  (~50 sec)

**Open (warm, smile, then pause):**
> "Hello everyone! My name is ______, from the **Gen AI team**."

> "I'm working on an agentic workflow called **Tuti** — it's an **Interactive Tutorial Builder**."

**The story (say it simply):**
> "So here's the idea. The world is moving from **markdown to HTML** — from plain reading material to rich, interactive pages. So I decided: why not convert the reading materials — the ones written in markdown — into **interactive tutorials in HTML**?"

> "And these tutorials aren't just text. Each one has the **content**, **visualisations**, **MCQs**, and **assessment questions** — all in one place."

**Set up the talk:**
> "In the next few minutes, I'll walk you through what Tuti is, what I learned building it, and the journey I took."

**➡️ NEXT**

---

## SLIDE 2 — The Problem  (~50 sec)

> "In our current system, most of the learning content is written in **markdown** files."

> "Now, markdown is great for *writing* — but it has a few real limitations when it comes to the learning *experience*."

**(point to the "static" cards)**
> "First, markdown is completely **static**. It only supports text and basic formatting."

> "So even if the concept is complex, it still looks like a long scroll of text — no interaction, no step-by-step learning, no engagement."

> "So the real problem is this: we already have good learning content — but it's **trapped in a static, text-only format**."

**(transition to the goal)**
> "The goal of Tuti is to convert this into a guided, **interactive tutorial experience** — where content, visuals, quizzes, and assessments all work together as a single flow."

**➡️ NEXT**

---

## SLIDE 3 — What is Tuti  (~50 sec)

> "So here's what Tuti actually does."

> "You upload a session — a **PowerPoint or an HTML page** — plus any extra reading material. That's it."

> "Then Tuti splits it into logical blocks, rewrites each one into clean interactive content, turns the concept diagrams into **animations**, adds **quizzes** to check understanding, and finishes with an **assessment**."

*(gesture to the screenshot)*
> "And this is the actual tool — clean and simple. Course, session, upload, done."

**Transition:**
> "Let me show you what the learner actually gets."

**➡️ NEXT**

---

## SLIDE 4 — See it: the output  (~50 sec)

*(point to the tutorial screenshot)*
> "This is a real tutorial Tuti generated. Notice four things."

> "**One** — content is revealed step by step, not dumped as a wall of text."
> "**Two** — the concept diagrams become **animations** that build up piece by piece."
> "**Three** — every step is gated by a **quiz** — you answer to continue, so you can't just scroll past."
> "**Four** — it ends with an **assessment** that ties the whole session together."

> "And it's one self-contained file — it drops straight into a learning platform."

**Transition:**
> "Now — how does it actually build all this? That's the interesting part."

**➡️ NEXT**

---

## SLIDE 5 — How it works: the workflow  (~75 sec — the centerpiece)

*(point across the flow, left to right)*
> "Tuti isn't one big AI prompt. It's a **pipeline of specialized agents**, and it flows left to right."

> "It **ingests** the file and describes the images… **divides** it into blocks… then four agents take over — **Content**, **Animation**, **MCQs**, and **Assessment** — and finally it **publishes** the tutorial."

*(point to the purple lane)*
> "But here's the important part — **a human reviews every single step.** Six review gates. At each one you can **accept**, **reject**, or **improve** — a specific block, a specific animation, a specific question."

*(trace the orange loop)*
> "And when you ask for a change, it loops back and **regenerates just that piece.**"

*(point to the two boxes)*
> "Two things support the whole flow. On the left, **memory** — it remembers your feedback, so a correction is made *once*, never asked again. On the right, **evaluation** — every output is scored against a rubric, and if it's below the bar, it regenerates *automatically*, before you even see it."

> "It's built on **LangGraph**, so any run can pause at a gate and resume exactly where it stopped."

**➡️ NEXT**

---

## SLIDE 6 — The agents  (~45 sec)

> "Quick look at the specialists — each has *one* job and its own quality bar."

> "The **Block Divider** groups the session into a few clean teaching blocks."
> "**Agent 1** writes the content — and critically, it uses the source *only*, it never invents."
> "**Agent 2** is a **vision** model — it looks at your diagrams and recreates them as clean animations."
> "**Agent 3** writes the quizzes, **Agent 4** writes the assessment."
> "And **the Judge** scores everything and pushes the others to fix their own work."

**➡️ NEXT**

---

## SLIDE 7 — Trust & quality  (~45 sec)

> "This slide is really about *trust* — because AI output you can't trust is useless."

> "So: **you review at every stage.** You have **per-element control** — fix one block without touching the rest. The agents **self-validate** against a rubric and regenerate when they fall short. And **course memory** means your feedback sticks."

*(point to screenshot)*
> "This is one of those review screens — you're always in control."

**➡️ NEXT**

---

## SLIDE 8 — Under the hood  (~40 sec)

> "For the builders in the room — a quick peek under the hood."

> "**Six** human gates, **five** agents, **seven** rubric eval-sets, **two** input formats."

> "It runs on LangGraph, a vision-capable Claude model, FastAPI with live updates, a React UI, and Supabase for storage. Every run is **persisted, resumable, and observable** — you can even watch the live cost."

**➡️ NEXT**

---

## SLIDE 9 — Key learnings  (~55 sec)

> "Now the part I found most interesting — what building this actually *taught* me."

> "**One — fidelity beats fluency.** The hard part isn't making the AI *write*. It's making it stay *strictly* to the source. My fix: give the reviewer the source and force a grounding pass — so it stops 'helpfully' making things up."

> "**Two — humans in the loop beat full autonomy.** A human check at every stage produced far more trustworthy results than letting it run on its own."

> "**Three — evaluations are the spec.** Writing rubrics turned a vague 'make it good' into something I could actually *measure* — and enforce."

> "**Four — the model and the prompts really matter.** Quality jumped when I moved to a stronger model and told it to *revise this exact item* instead of starting over."

**➡️ NEXT**

---

## SLIDE 10 — The journey  (~50 sec)

> "So how did I get here? Four phases."

> "**First**, a walking skeleton — I wired the whole pipeline end to end with a fake AI, before making any single part good."
> "**Then** I built the real agents and the animations."
> "**Then** the quality layer — the evaluations, the six human gates, per-element control."
> "**And finally** memory, a clean interface, and a lot of polish — fixing real problems like content drifting off-source and animations that were too text-heavy."

*(gesture to screenshot)*
> "And here's the library of tutorials it's produced."

**➡️ NEXT**

---

## SLIDE 11 — Takeaways & Thank you  (~40 sec)

> "So, to wrap up — three takeaways."

> "**One** — the winning pattern was **specialized agents, plus evaluations, plus human gates, plus memory** — not one giant prompt."
> "**Two** — **quality is engineered.** Through grounding, rubrics, and review — not hoped for."
> "**Three** — it's **production-shaped**: resumable, persisted, observable, with a clean UI."

**Close (warm, confident):**
> "Tuti turns any session into a guided, assessed tutorial — reliably. Thank you! I'd love to take your questions."

**➡️ (stay on this slide for Q&A)**

---

### If someone asks: "Why not just one big AI call?"
> "Because you lose control and quality. Splitting it into agents lets each one specialize, lets me score each output, and lets a human fix one piece without breaking the rest."

### If someone asks: "How do you stop it from making things up?"
> "Two ways — the writing agent is told to use the source only, and the reviewer literally gets the source to check against. Anything ungrounded gets flagged and regenerated."

### If someone asks: "Can it handle any subject?"
> "Yes — it works from whatever's in the deck or reading material, so it's subject-agnostic. I tested it on things like SDLC models and AI agents."
