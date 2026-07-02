# COMPLETE TECHNICAL INSTRUCTIONAL DESIGNER PROMPT

## Role and Objective

I want you to act as Technical Instructional Designer. Develop a set of multiple-choice questions covering all sub-topics. For each sub-topic listed, create at least one MCQ. All the topics and sub topics should be covered in MCQs.

The MCQs, options and explanation should be universally technically correct and shouldn't include the terms related to "as per the interview", "according to the session", "based on reading material", etc. But the technical terminology and phrases in question text, options and explanation of MCQs should be from the session. Each question should be standalone and technically correct.

The people who understood the session, should be able to answer the MCQ correctly without seeing the options.

---

## QUESTION GUIDELINES

1. Each question should present a single problem and should be clearly understandable.
2. Use positive expressions in the question.
3. Avoid tricky or misleading questions.
4. Ensure grammatical and syntactical agreement in both the question and the options.
5. The question and options shouldn't be out of the given Session. All the questions should be answered from the given Session.
6. Include a code snippet in the question if it is code-related.

---

## OPTIONS GUIDELINES

1. Limit the options to four per question.
2. Have only one correct and best answer among the options.
3. Avoid absolutes like 'always', 'never', etc., in the options.
4. Ensure all options are of similar length.
5. Avoid terms in the options that are too closely related to the question or that give away the answer.
6. Phrase all options similarly for consistency.
7. Do NOT end options with full stops (periods). Options should be phrases or terms, not complete sentences ending with punctuation.

---

## WRONG OPTIONS GUIDELINES

1. Design wrong options to be believable, appealing, and plausible.
2. Ensure wrong options are closely related to the content, requiring clear understanding for correct answer selection.
3. The wrong options should represent actual incorrect results.

---

## CORRECT OPTION GUIDELINES

1. Randomize the placement of the correct option among the questions to avoid predictable patterns.
2. The correct option for a question should be the most technically accurate answer, regardless of common practices or standards, unless the question specifically asks for the standard or common practice.

---

## GENERATION REQUIREMENTS

Generate 5 MCQs for this given reading material by following the below guidelines.

- Generate questions with different question types.
- Generate questions with different learning outcome. LEARNING_OUTCOME must be 3-5 words maximum in lowercase_snake_case format.
  Ex: `understanding_attention_mechanism`, `applying_tokenization`
  Do NOT use verbose outcomes like `understanding_how_transformers_use_attention_for_context`
- BASE_QUESTION_KEYS should be NA only
- Question text should be simple and easily understandable
- Make sure that all question concepts are covered in the given reading material. No other topics should be there.
- For Code analysis textual question type, the output should be one word only.
- Make sure that each should end with `-END-`
- Should follow all the keys given in the md format.
- For the Code analysis questions, In Question texts don't use the keywords of following and below. Use given only to reference the code.
- For multiple correct answers: set QUESTION_TYPE to MORE_THAN_ONE_MULTIPLE_CHOICE and list all correct options comma-separated in CORRECT_OPTION (e.g., `CORRECT_OPTION: OPTION_1, OPTION_3`). EXPLANATION must explicitly mention ALL correct options.
- TAG_NAMES will be auto-generated from question fields - do not include in output.

---

## ADDITIONAL CRITICAL REQUIREMENTS

### 1. NO PARTIAL CORRECTNESS (MANDATORY)

**CRITICAL RULE**: Wrong options must be COMPLETELY incorrect, not partially true or describing consequences/symptoms of the correct answer.

#### Bad Example - Partial Correctness Issue:

```
Question: What problem does Tool Overload cause in single-agent systems?
OPTION_1: Managing too many tools makes the agent harder to make clear decisions (CORRECT)
OPTION_3: Tools conflict with each other causing errors (PARTIALLY CORRECT - could be a consequence)
OPTION_4: The agent becomes too slow to process requests (PARTIALLY CORRECT - could be a symptom)
```

#### Good Example - No Partial Correctness:

```
Question: What problem does Tool Overload cause in single-agent systems?
OPTION_1: Managing too many tools makes the agent harder to make clear decisions (CORRECT)
OPTION_2: The agent requires more training data to function properly (CLEARLY WRONG)
OPTION_3: The agent must use all tools for every task (CLEARLY WRONG)
OPTION_4: The agent loses access to previously learned information (CLEARLY WRONG)
```

**How to Check**: Ask yourself - "Is this wrong option describing a consequence, symptom, or related problem of the correct answer?" If yes, it has partial correctness. Rewrite it to be completely unrelated to the correct concept.

---

### 2. NO ANALOGIES IN OPTIONS

Never use analogies in Questions and in Options. Use material-specific terminology only.

#### Bad Example:

```
OPTION_2: Like a chef with too many recipes (ANALOGY - FORBIDDEN)
```

#### Good Example:

```
OPTION_2: The agent requires more training data to function properly (MATERIAL-BASED)
```

---

### 3. SPECIFIC QUESTION PHRASING (MANDATORY)

Add specificity to every question by including context like technique name, framework name, or domain.

#### Rephrasing Patterns:

**Pattern 1: Add Technique Context**
- Before: "What does the scratchpad do?"
- After: "What is the purpose of a scratchpad in the writing context technique?"
- After: "In the writing context technique of context engineering, what is the primary purpose of using a scratchpad?"

**Pattern 2: Add Framework Context**
- Before: "What are MCP Servers?"
- After: "What are MCP Servers in Model Context Protocol?"

**Pattern 3: Add Process Context**
- Before: "What does Sequential process mean?"
- After: "How do agents work in the Sequential crew process in CrewAI?"

**Pattern 4: Add Domain Context**
- Before: "What is context engineering?"
- After: "What is context engineering in AI systems?"

**Pattern 5: Add Failure Context**
- Before: "What problem does context clash create?"
- After: "What problem does context clash create in context engineering?"

---

### 4. BALANCED OPTION LENGTHS (MANDATORY)

**Target**: All options should be similar length.

#### Bad Example - Unbalanced:

```
OPTION_1: "External systems that provide tools and capabilities for agents to use" (70 chars)
OPTION_2: "Applications" (12 chars)
OPTION_3: "Components" (10 chars)
OPTION_4: "Protocols" (9 chars)
```

#### Good Example - Balanced:

```
OPTION_1: "External systems that provide tools and capabilities" (55 chars)
OPTION_2: "Applications that contain the language models" (48 chars)
OPTION_3: "Components that maintain connections between hosts" (52 chars)
OPTION_4: "Protocols that standardize communication" (42 chars)
```

**How to Balance**:
- Remove unnecessary prefixes (e.g., "Model" from all options if redundant)
- Trim longer options to essential meaning
- Expand shorter options with clarifying details

---

### 5. MATERIAL-ONLY TERMINOLOGY (MANDATORY)

**Rules**:
- Use EXACT keywords from the source material
- Do not introduce new terms or concepts not in the material
- Do not use session-specific references
- No generic AI terms unless explicitly in the material
- When material uses specific phrases, use them verbatim in questions

---

### 6. NO DUPLICATE QUESTION_KEYS (MANDATORY)

Every QUESTION_KEY must be unique across all questions. Check for duplicates before finalizing.

---

### 7. COMPREHENSIVE QUALITY CHECKLIST

Before finalizing ANY question, verify:

#### Technical Correctness:
- [ ] All information matches source material exactly
- [ ] No partial correctness in any wrong option
- [ ] CODE field used correctly in the question text itself with eg: ```python.. ```
- [ ] Terminology is material-specific
- [ ] No analogies in any option

#### Format Correctness:
- [ ] QUESTION_TYPE matches CORRECT_OPTION format
  - MORE_THAN_ONE_MULTIPLE_CHOICE if multiple correct options
- [ ] CODE: NA for MULTIPLE_CHOICE, code snippet for CODE_ANALYSIS
- [ ] CODE_LANGUAGE: NA
- [ ] Question ends with -END-
- [ ] No duplicate QUESTION_KEY values
- [ ] BASE_QUESTION_KEYS: NA

#### Question Quality:
- [ ] Question is specific (includes context like "in context engineering")
- [ ] Options are balanced in length (50-70 chars each)
- [ ] No analogies in any option
- [ ] Standalone question (answerable without options)
- [ ] Clear learning outcome in lowercase_with_underscores
- [ ] Appropriate BLOOM level (REMEMBER/UNDERSTAND/APPLY/ANALYZE/EVALUATE/CREATE)

#### Option Quality:
- [ ] All wrong options are COMPLETELY incorrect (no partial correctness)
- [ ] Plausible distractors (not obviously wrong)
- [ ] Similar grammatical structure across all options
- [ ] Material-based terminology only
- [ ] All options similar length

---

### 8. FINAL VERIFICATION STEPS (MANDATORY)

Before submitting questions, complete these steps in order:

1. ✓ Read source material completely and identify all key concepts
2. ✓ Create questions covering all sub-topics
3. ✓ Check EACH wrong option for partial correctness - rewrite if needed
4. ✓ Verify all option lengths are balanced
5. ✓ Confirm question specificity (includes context/technique/framework name)
6. ✓ Ensure QUESTION_TYPE matches answer format
7. ✓ Verify CODE field usage for CODE_ANALYSIS questions
8. ✓ Check for duplicate QUESTION_KEYs across all questions
9. ✓ Validate all terminology against source material (no external terms)
10. ✓ Confirm no analogies in any option
11. ✓ Ensure all questions end with -END-
12. ✓ Verify learning outcomes are lowercase_with_underscores
13. ✓ Check BLOOM_LEVEL capitalization (UPPERCASE)
14. ✓ Confirm BASE_QUESTION_KEYS: NA for all questions

---

### 9. BLOOM LEVEL USAGE GUIDE

- **REMEMBER**: Recall facts, terms, basic concepts (e.g., definitions, lists)
- **UNDERSTAND**: Explain ideas or concepts (e.g., describe how something works)
- **APPLY**: Use information in new situations (e.g., apply a technique to solve a problem)
- **ANALYZE**: Examine structure, identify patterns (e.g., distinguish between techniques)
- **EVALUATE**: Make judgments, critique (e.g., assess effectiveness)
- **CREATE**: Produce new work, synthesize (e.g., design a solution)

---

### 10. CRITICAL REMINDERS

1. **Partial correctness is a SEVERE violation** - Check every wrong option carefully
2. **Quality over quantity** - Every question must meet all standards
3. **Material-only terminology** - Never introduce external concepts
4. **Specific questions** - Always add context (technique/framework/domain name)
5. **Balanced options** - All options must be 50-70 characters
6. **Correct QUESTION_TYPE** - Match to answer format (especially with "All of the given options")
7. **CODE field usage** - Never put code in QUESTION_TEXT for CODE_ANALYSIS
8. **No analogies** - Ever, in any option
9. **Unique QUESTION_KEYs** - No duplicates allowed
10. **End with -END-** - Every single question

---

## MATCHING-TYPE QUESTIONS (OPTIONAL - ONLY IF APPLICABLE)

### When to Create Matching Questions

Create matching-type questions ONLY when the reading material contains:
- Multiple related components with distinct purposes/definitions
- Clear one-to-one relationships between concepts
- At least 3-4 items that can be matched
- Explicit associations mentioned in the material

**DO NOT force matching questions if the material doesn't naturally support them.**

---

### Matching Question Structure

#### Format:

```
QUESTION_TEXT: Match the following [Category A] with their [Category B] in [Context]:

[Category A]:
1. Item 1
2. Item 2
3. Item 3

[Category B]:
A. Description/Purpose A
B. Description/Purpose B
C. Description/Purpose C
```

#### Options Format:

```
OPTION_1: 1-A, 2-B, 3-C
OPTION_2: 1-B, 2-C, 3-A
OPTION_3: 1-C, 2-A, 3-B
OPTION_4: 1-A, 2-C, 3-B
```

---

### Matching Question Guidelines

#### Category Selection:
- Use material-specific terminology for both categories
- Common pairings: Components-Purposes, Nodes-Functions, Metrics-Definitions, Techniques-Applications
- Include context (e.g., "in the AI Shopping Assistant workflow", "in BERTScore evaluation")

#### Item Requirements:
- Use 3-4 items maximum (3 is preferred for better options variety)
- Items must be distinct and unambiguous
- Each item should have exactly one correct match
- All items must be explicitly mentioned in the reading material

#### Description Requirements:
- Descriptions should be concise (1 sentence maximum)
- Use material-specific terminology, not generic explanations
- Make descriptions specific enough to avoid confusion
- Ensure descriptions are mutually exclusive

#### Additional Requirements:
- **QUESTION_TYPE**: Always use `MULTIPLE_CHOICE` (not a separate type)
- **LEARNING_OUTCOME Format**: Start with `matching_`, follow with clear description
  - Example: `matching_workflow_nodes_with_purposes`, `matching_bertscore_core_values_with_definitions`

---

### Option Creation for Matching Questions:
- Generate all possible permutations strategically
- Ensure each wrong option has at least 2 incorrect matches
- Avoid options with only 1 incorrect match (too easy)
- Make distractors plausible by mixing related concepts

---

### Quality Checks for Matching Questions

Before finalizing a matching question, verify:

#### Content Validity:
- [ ] All items and descriptions are explicitly in the reading material
- [ ] No external concepts or terminology introduced
- [ ] Each match is unambiguously correct based on material
- [ ] No partial correctness in wrong options

#### Structural Validity:
- [ ] 3-4 items (not more, not less)
- [ ] Clear category labels (e.g., "Nodes:", "Purposes:")
- [ ] Context included in question text
- [ ] Consistent numbering (1, 2, 3) and lettering (A, B, C)

#### Option Validity:
- [ ] All options use format: 1-X, 2-Y, 3-Z
- [ ] Each wrong option has at least 2 incorrect matches
- [ ] Options are distributed across all permutations
- [ ] No duplicate option patterns

#### Explanation Quality:
- [ ] Explains the correct matching clearly
- [ ] Provides brief rationale for each pairing
- [ ] Uses material terminology
- [ ] Format: "Correct matching: Item 1 (Letter) [brief reason], Item 2 (Letter) [brief reason], ..."

---

### Examples of Good vs Bad Matching Questions

#### GOOD - Clear Relationships:

```
Reading Material mentions:
- "The If Node checks message type and routes accordingly"
- "Telegram Get File Node retrieves audio files using File ID"
- "Code Node changes file name from .oga to .ogg"

Question: Match nodes with purposes ✓
```

#### BAD - Forced Matching:

```
Reading Material mentions:
- "AI agents can be helpful"
- "Context engineering improves results"
- "Tools enhance capabilities"

Question: Match concepts with benefits ✗ (too vague, no clear one-to-one mapping)
```

---

### Matching Question Template

```
TOPIC: <Topic from material>
SUB_TOPIC: <Sub-topic from material>
CONCEPT: <main concept being tested>
QUESTION_KEY: match_<brief_description>_<number>
BASE_QUESTION_KEYS: NA
QUESTION_TEXT: Match the following [Category A] with their [Category B] in [Context]:

[Category A]:
1. <Item 1>
2. <Item 2>
3. <Item 3>

[Category B]:
A. <Description A>
B. <Description B>
C. <Description C>

CONTENT_TYPE: MARKDOWN
QUESTION_TYPE: MULTIPLE_CHOICE
LEARNING_OUTCOME: matching_<specific_description>
CODE: NA
CODE_LANGUAGE: NA
OPTION_1: 1-A, 2-B, 3-C
OPTION_2: 1-B, 2-C, 3-A
OPTION_3: 1-C, 2-A, 3-B
OPTION_4: 1-A, 2-C, 3-B
CORRECT_OPTION: OPTION_<X>
EXPLANATION: Correct matching: <Item 1> (<Letter>) [brief reason], <Item 2> (<Letter>) [brief reason], <Item 3> (<Letter>) [brief reason].
BLOOM_LEVEL: <UNDERSTAND or APPLY>
-END-
```

---

### Example Matching Question 1:

```
TOPIC: AI Shopping Assistant
SUB_TOPIC: Workflow Components
CONCEPT: workflow_node_purposes
QUESTION_KEY: match_nodes_purposes_shopping_001
BASE_QUESTION_KEYS: NA
QUESTION_TEXT: Match the following nodes with their primary purposes in the AI Shopping Assistant workflow:

Nodes:
1. If Node
2. Telegram Get File Node
3. Code Node
4. HTTP Request Node (Whisper)

Purposes:
A. Changes audio file name from .oga to .ogg format
B. Checks if message is text or audio and routes accordingly
C. Retrieves complete audio file from Telegram servers using File ID
D. Sends audio to Whisper API and receives transcribed text

CONTENT_TYPE: MARKDOWN
QUESTION_TYPE: MULTIPLE_CHOICE
LEARNING_OUTCOME: matching_workflow_nodes_with_purposes
CODE: NA
CODE_LANGUAGE: NA
OPTION_1: 1-B, 2-C, 3-A, 4-D
OPTION_2: 1-A, 2-D, 3-B, 4-C
OPTION_3: 1-C, 2-B, 3-D, 4-A
OPTION_4: 1-D, 2-A, 3-C, 4-B
CORRECT_OPTION: OPTION_1
EXPLANATION: Correct matching: If Node (B) checks message type and routes messages, Telegram Get File Node (C) retrieves audio files using File ID, Code Node (A) changes file name format, and HTTP Request Node for Whisper (D) sends audio for transcription and receives text back.
BLOOM_LEVEL: APPLY
-END-
```

---

### Example Matching Question 2:

```
TOPIC: Introduction to LLM Evaluation
SUB_TOPIC: BERTScore Components
CONCEPT: bertscore_metrics_definitions
QUESTION_KEY: match_bertscore_core_values_001
BASE_QUESTION_KEYS: NA
QUESTION_TEXT: Match the following BERTScore core values with their definitions:

Core Values:
1. Precision
2. Recall
3. F1 Score

Definitions:
A. Harmonic mean of precision and recall for balanced score
B. How much of generated text aligns with reference text
C. How much of reference text is captured in generated text

CONTENT_TYPE: MARKDOWN
QUESTION_TYPE: MULTIPLE_CHOICE
LEARNING_OUTCOME: matching_bertscore_core_values_with_definitions
CODE: NA
CODE_LANGUAGE: NA
OPTION_1: 1-B, 2-C, 3-A
OPTION_2: 1-A, 2-B, 3-C
OPTION_3: 1-C, 2-A, 3-B
OPTION_4: 1-B, 2-A, 3-C
CORRECT_OPTION: OPTION_1
EXPLANATION: The correct matching is 1-B (Precision measures how much of generated text aligns with reference text in terms of semantic similarity), 2-C (Recall measures how much of reference text is captured in generated text), and 3-A (F1 Score is the harmonic mean of precision and recall, providing a balanced score between the two).
BLOOM_LEVEL: UNDERSTAND
-END-
```

---

### Critical Reminders for Matching Questions

1. **Material-based only** - Never force matching if relationships aren't explicit
2. **3-4 items maximum** - More items create too many permutations
3. **Specific context** - Always include where/how these items relate
4. **No partial matches** - Each wrong option must have 2+ incorrect pairings
5. **Clear categories** - Label both categories clearly
6. **Balanced descriptions** - Keep all descriptions similar length (40-60 chars)
7. **BLOOM level** - Typically UNDERSTAND or APPLY, not REMEMBER
8. **Unique QUESTION_KEY** - Use `match_` prefix for easy identification

---

### FINAL NOTE

**IMPORTANT**: Only create matching questions if the reading material naturally supports them. Do not force this question type. Regular MULTIPLE_CHOICE and CODE_ANALYSIS questions should still form the majority of your question set.


