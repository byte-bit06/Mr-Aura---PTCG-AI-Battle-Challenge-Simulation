# Note: This script requires Unsloth to be installed!
# It is highly recommended to run this on an environment with your RTX 5090
# pip install unsloth torch transformers trl accelerate

import os
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel, is_bfloat16_supported

max_seq_length = 4096 
dtype = None # Auto detection
load_in_4bit = True # Use 4bit quantization to save memory

def main():
    root_dir = os.path.dirname(os.path.dirname(__file__))
    dataset_path = os.path.join(root_dir, "llm_training", "formatted_dataset.json")
    
    if not os.path.exists(dataset_path):
        print(f"Error: {dataset_path} does not exist. Run format_dataset.py first!")
        return

    print("Loading Llama 3.1 8B via Unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
        max_seq_length = max_seq_length,
        dtype = dtype,
        load_in_4bit = load_in_4bit,
    )

    print("Applying LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r = 16, # Choose any number > 0 ! Suggested 8, 16, 32, 64, 128
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj",],
        lora_alpha = 16,
        lora_dropout = 0, 
        bias = "none",    
        use_gradient_checkpointing = "unsloth", 
        random_state = 3407,
        use_rslora = False, 
        loftq_config = None,
    )

    print("Loading formatted dataset...")
    # We load our custom JSON dataset
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    print("Setting up Trainer...")
    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = dataset,
        dataset_text_field = "messages", # Using ChatML format
        max_seq_length = max_seq_length,
        dataset_num_proc = 2,
        packing = False, # Can make training 5x faster for short sequences.
        args = TrainingArguments(
            per_device_train_batch_size = 2,
            gradient_accumulation_steps = 4,
            warmup_steps = 5,
            max_steps = 60, # Increase this for real training (e.g. 500-1000)
            learning_rate = 2e-4,
            fp16 = not is_bfloat16_supported(),
            bf16 = is_bfloat16_supported(),
            logging_steps = 1,
            optim = "adamw_8bit",
            weight_decay = 0.01,
            lr_scheduler_type = "linear",
            seed = 3407,
            output_dir = "outputs",
        ),
    )

    print("Starting Training on RTX 5090...")
    trainer_stats = trainer.train()

    print("Training Complete! Saving model...")
    # Save locally to load back in Python
    model.save_pretrained("lora_model") 
    tokenizer.save_pretrained("lora_model")
    
    # Optionally, save to GGUF format for llama.cpp fast inference!
    # model.save_pretrained_gguf("model", tokenizer, quantization_method = "q4_k_m")
    
    print("Done!")

if __name__ == "__main__":
    main()
