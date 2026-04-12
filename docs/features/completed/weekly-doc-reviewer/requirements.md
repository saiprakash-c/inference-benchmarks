# Goal

We wanted to have a weekly doc reviewer that kinda extensively checks if the docs are in sync with the code and also if we are following our core-beliefs and the architecture. We also have doc_reviewer that does this job for every PR but the docs will drift eventually, so we want to have this weekly doc reviewer catch. 

# Requirements

- Setup in github to run weekly. I am not sure if it's possible. Let me know if not. We can think of some alternate. 
- Also have a script that i can run locally inside dev/rt dockers
- It should produce output similarly ot ci doc_reviewer that a agent can take and correct docs. 
- The agent should only update docs. If code doesn't abide by core-beliefs, then the agent shouldn't correct it and ask for permission from the human before proceeding what to do. 