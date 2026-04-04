# Goal

I want to simplify feature workflow so that i know what i exactly asked for in requirements.md, what agent modified on top of it and what exactly i approved for in plan.md and what agent modified on top. 

# Requirements

- Agent should not touch requirements.md. That is only written by the human
- There should be only document called plan.md that contains both the design and the execution plan. 
- Any additions/subtractions on the requirements should be on top of the plan.md and agent should rationalize why it had to do that way. 
- plan.md should have a clear sections no matter what. Requirements from User, Updates on User Requirements, Design, Tasks, Updates on approved Plan,
- Updates on User Requirements should be where the agent should update human given requirements with rationale. 
- Design should be mostly visual. Text is allowed minimally to explain. 
- Tasks should be a checklist that agent should follow to complete the feature. 
- The plan.md should be concise for a quick review. 
- Agent once finishing plan.md should ask the human for review. Once approved, it should go to active and agent should start working on it ticking the checklist as it goes along. Any modifications it realizes it needs to do on the plan plan.md should have a clear section at the bottom Updates on Approved Plan without touching the approved plan. 