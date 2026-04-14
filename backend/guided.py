import re
import os
import json
from typing import Dict, Any
from ai_core import call_model

DOCUMENT_TYPES = ["Lease", "Sublease", "Roommate Agreement", "Promissory Note", "Sale Contract", "Commission Agreement", 
                  "Service Contract", "Independent Contractor Agreement", "Living Will", "Last Will and Testament", 
                  "Temporary Guardianship or Childcare Consent Form", "Store Policies", "Terms of Service"]

CONFIRM_YES = ["yes", "correct", "y"]
CONFIRM_NO = ["no", "wrong", "n"]
CONFUSION = ["i don't understand", "what does", "confused", "simpler", "explain", "?"]


def handle_chat(req: Dict[str, Any]) -> Dict[str, Any]:
    stage = req.get("stage", "classifying")
    doc_type = req.get("doc_type")
    previous_answers = req.get("previous_answers", {})
    user_text = req.get("text", "").strip()

   
    if stage == "classifying":
        system_prompt = f"""
        You are a legal document classification assistant.
        Select the SINGLE best matching document type from {DOCUMENT_TYPES}.
        Explain clearly what the document does in simple terms but a minimum of 3 sentences.

        Return ONLY valid JSON:

        {{
            "doc_type": "...",
            "explanation": "..."
        }}
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
        try:
            response = call_model(messages)
            parsed = json.loads(response.strip())
        except Exception:
            parsed = {
                "doc_type": "Unknown",
                "explanation": "Unable to find a matching document. Please provide more detail."
            }

        if parsed["doc_type"] not in DOCUMENT_TYPES:
            parsed["doc_type"] = "Unknown"
            parsed["explanation"] = "Unable to help create the document suggested. Please consult a professional lawyer."

        return {
            "doc_type": parsed["doc_type"],
            "stage": "confirmation", # next stage
            "previous_answers": previous_answers, 
            "message": f"{parsed['explanation']}\n\nDoes this document type match your situation?\n\nPlease respond with 'yes' or 'no' to continue."
        }
    
    
    if stage == "confirmation":
        answer = user_text.lower()

        if answer in CONFIRM_YES and doc_type:
            return {
                "doc_type": doc_type,
                "stage": "jurisdiction",
                "previous_answers": previous_answers,
                "message": "Before we continue, what state or city will this document be used in?"
            }
        elif answer in CONFIRM_NO:
            return {
                "doc_type": None,
                "stage": "classifying",
                "message": "No problem. Please describe your situation again in more detail."
            }
        else:
            return {
                "doc_type": doc_type,
                "stage": "confirmation",
                "message": "Please respond with 'yes' or 'no' to continue."
            }
    
    if stage == "jurisdiction" and doc_type:
        previous_answers["jurisdiction"] = user_text

        blueprint_prompt = f"""
        Generate a structured JSON blueprint for drafting a {doc_type}.

        Each section must include:
        - title
        - explanation_basic (2-4 simple but informative sentences). Explain what protections this clause gives, do not just list what the questions included will be.
        - questions (list of strings) that cover common clauses included in the document based on the user's {user_text}.
        
        In case requested by the user, also includes:
        - explanation_simplified (2-3 sentences, minimal legal terms)
        - explanation_detailed (3-4 sentences, more detailed legal terminology)
        - example if necessary
        - uncommon clauses based on the user's previous_answers
     

        Example of questions that cover uncommon clauses:
        If the document is a leasing agreement, can they have guests over, are pets and smoking allowed?
        Similarly, when do visitation hours end? Who covers damages? Does the user have any allergies?

        Return ONLY valid JSON:

        {{ "sections": [ ... ] }}

        Do not provide legal advice.
        """
        try:
            response = call_model([
                {"role": "system", "content": blueprint_prompt}
            ])
            parsed = json.loads(response.strip())
            sections = parsed.get("sections", [])
        except Exception:
            sections = []

        if not sections:
            return {
                "stage": "classifying",
                "message": "There seems to be an issue on our end. Please try again."
            }

        first_section = sections[0]
        
        if not first_section.get("questions"):
            return {
                "stage": "classifying",
                "message": "Error generating questions. Please try again."
            }
        
        first_question = first_section["questions"][0]

        return {
            "doc_type": doc_type,
            "stage": "collection",
            "previous_answers": {
                "answers": {},
                "sections": sections,
                "current_question": 0,
                "current_section": 0,
                "jurisdiction": user_text
            },
            "message": (
                f"Let's begin drafting your {doc_type}.\n\n"
                f"{first_section['title']}\n\n"
                f"{first_section['explanation_basic']}\n\n"
                f"Question 1: {first_question}"
            )
        }

    if stage == "collection" and doc_type:
        sections = previous_answers.get("sections", [])
        answers = previous_answers.get("answers", {})
        section_index = previous_answers.get("current_section", 0)
        question_index = previous_answers.get("current_question", 0)

        if not sections:
            return {
                "stage": "classifying", 
                "message": "Session expired. Please start again."
            }
        if section_index >= len(sections):
            return {
                "stage": "classifying",
                "message": "Section flow error. Please restart."
            }

        section = sections[section_index]
        questions = section.get("questions", [])

        if not questions:
            return {
                "stage": "classifying",
                "message": "No questions found. Please restart."
            }

        if question_index >= len(questions):
            return {
                "stage": "classifying",
                "message": "Question flow error. Please restart."
            }

        current_question = questions[question_index]

        intent_prompt = f"""
        You are classifying a user response during a legal document questionnaire.
        Determine the user's intent.

        Possible intents:
        - answer (they are answering the question asked)
        - clarification (they want an explanation of the clause or question asked)
        - question (they are asking a legal question)

        Return ONLY valid JSON:

        {{
         "intent": "answer | clarification | question"
        }}

        User input: {user_text}
        """
        try:
            response = call_model([
                {"role": "system", "content": intent_prompt},
                {"role": "user", "content": user_text}
            ])
            parsed_intent = json.loads(response.strip())
            intent = parsed_intent.get("intent", "answer")
        except:
            intent = "answer"

        if intent == "clarification":
            explain_prompt = f"""
            Explain in 2-3 sentences what the following legal clause or question typically covers or protects in simple terms.
            Do not simply list the questions covered.

            Section: {section['title']}
            Clause: {section['explanation_basic']}
            User question: {user_text}

            Do not give legal advice.
            """
            response = call_model([
                {"role": "system", "content": explain_prompt}
            ])
            explanation = response.strip()
            
            return {
                "stage": "collection",
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "message": f"""{explanation}

                Let's continue.
    
                Question {question_index+1}: {current_question}
                """
            }

        if intent == "question":
            q_prompt = f"""
            The user is filling out a {doc_type}.
            They asked a question while filling out the document.

            Answer the question directly and clearly (2–4 sentences).

            If relevant, relate it to the current question:
            "{current_question}"

            Do NOT explain the clause unless it is directly relevant.
            Do NOT give legal advice.

            Question: {user_text}
            """
            response = call_model([
                {"role": "system", "content": q_prompt}
            ])
            answer_text = response.strip()

            return {
                "stage": "collection",
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "message": f"""{answer_text}

                Let's continue.

                Question {question_index+1}: {current_question}
                """
            }

        answers.setdefault(f"section_{section_index}", {})
        answers[f"section_{section_index}"][f"question_{question_index}"] = user_text
        previous_answers["answers"] = answers
        question_index += 1
        previous_answers["current_question"] = question_index

        # handles nxt question or next section
        if question_index < len(questions):
            next_question = questions[question_index]
            return {
                "stage": "collection", 
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "message": f"Question {question_index+1}: {next_question}"
            }

        next_section_index = section_index + 1
        if next_section_index < len(sections):
            next_section = sections[next_section_index]
            previous_answers["current_section"] = next_section_index
            previous_answers["current_question"] = 0
            return {
                "stage": "collection", 
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "message": (
                    f"{next_section['title']}\n\n"
                    f"{next_section['explanation_basic']}\n\n"
                    f"Question 1: {next_section['questions'][0]}"
                )
            }

        return {
            "stage": "additional_provisions", 
            "doc_type": doc_type,
            "previous_answers": previous_answers,
            "message": (
                "All sections are complete.\n\n"
                "Would you like to add any additional provisions or custom terms?\n\n"
                "If yes, please describe them. If not, type 'no' to continue."
            )
        }

    if stage == "additional_provisions" and doc_type:
        text = user_text.strip()
        answers = previous_answers.get("answers", {})
        sections = previous_answers.get("sections", [])

        clean_text = text.strip().lower()
        additional = "" if clean_text in CONFIRM_NO else text

        drafting_prompt = f"""
        You are a legal document drafting assistant.

        Generate a COMPLETE {doc_type} in plain text, no markdown or formatting syntax, using the name of the sections and ONLY the user provided answers.
        Do NOT invent or fill in any information not explicitly given by the user.
        Include additional provisions if provided.
        Do not give legal advice.

        Rules:
        - Use clear headings like {doc_type} at the top, section titles as subheadings
        - Paragraphs for content
        - Numbered or bulleted lists only if needed
        - Avoid HTML or markdown (*, -)
        - Make it professional and legible

        Sections:
        {sections}

        Answers:
        {answers}

        Additional provisions:
        {additional}
        """
        response = call_model([
            {"role": "system", "content": drafting_prompt}
        ])
        draft = response.strip()
        previous_answers["document"] = draft

        return {
            "stage": "editing", 
            "doc_type": doc_type,
            "document": draft, 
            "previous_answers": previous_answers,
            "message": (
                "Your draft is ready.\n\n"
                "You can edit the document directly or tell me what changes you'd like to make.\n\n"
                "When you are finished, type or click 'Done' to finalize your document."
            )
        }

    if stage == "editing":
        document = previous_answers.get("document", "")
    
        if user_text.lower() == "done":
            return {
                "stage": "complete",
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "document": document,
                "message": "Your document is ready."
            }
    
        edit_prompt = f"""
        You are editing a legal document.

        Current document:
        {document}

        User request:
        {user_text}

        Instructions:
        - Apply the requested changes to the document
        - Keep structure intact, do not add any markdown (*, -)
        - Do not remove content unless related to the changes requested
        - Do NOT invent or fill in any information not explicitly given by the user.
        - If a field is missing, leave a blank line: _________________________
        - Return updated document
        """
        response = call_model([
            {"role": "system", "content": edit_prompt}
        ])
        updated_doc = response.strip()
        previous_answers["document"] = updated_doc

        return {
            "stage": "editing", 
            "doc_type": doc_type,
            "document": updated_doc, 
            "previous_answers": previous_answers,
            "message": "Document updated. Continue editing if needed."
        }
    
    if stage == "complete" and doc_type:
        if user_text.lower() != "done":
            return {
                "stage": "editing",
                "doc_type": doc_type,
                "previous_answers": previous_answers,
                "document": previous_answers.get("document", ""),
                "message": "You can continue editing your document. What would you like to change?"
            }
        return {
            "stage": "complete",
            "doc_type": doc_type,
            "previous_answers": previous_answers,
            "document": previous_answers.get("document", ""),
            "message": "Your document has already been generated. You can continue editing it if needed."
        }
    
    return {"stage": stage, "doc_type": doc_type, "previous_answers": previous_answers,
            "message": "Unhandled stage, please try again."}