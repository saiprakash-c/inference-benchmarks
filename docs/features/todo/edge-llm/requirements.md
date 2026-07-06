# Goal

Run a simple Qwen based model LLM using TensorRT Edge LLM. I want to understand teh basics of TensorRT Edge LLM

# Requirements. 

- Work should be done on a branch called saip/edge-llm
- Create a folder called experimental
- Create a simple C++ script that calls TensorRT Edge LLM API to load and run a Qwen based model 
- I call the script using bazel run //experimental:tutorial -- "can you explain tensor cores" and then the script should stream the answer back. 
- The script has to be so simple that it is very easy to understand. No bigger things yet. 
- Later on I will work with a bigger model and then use speculative decoding, paged attention etc. For now, it has to be dead simple. 
- Don't use CLI commands to run the model. It has to be C++ APIs