"""Build benchmark/prompts.jsonl: 1,000 prompts like a real customer-support chatbot gets.

Mix (by design, mirrors real support traffic):
  ~70% FAQ questions: 45 intents, each with 4 human-style paraphrases. Popular intents
       repeat a lot (Zipf distribution), people retype them with different casing.
  ~15% easy general requests (translate, define, small talk).
  ~15% hard requests (multi-step planning, code, analysis, long writing).
Run once; the file is committed so results are reproducible.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(2026)
OUT = Path(__file__).resolve().parent / "prompts.jsonl"
SYSTEM = ("You are the customer-support assistant for ShopEasy, an Indian online store. "
          "Answer clearly and briefly (under 120 words). If you don't know store-specific details, say so and suggest contacting support.")

FAQ = {
    "reset_password": ["How do I reset my password?", "I forgot my password, how can I reset it?", "Can't log in, forgot password. Help?", "What's the process to change a forgotten password?"],
    "track_order": ["How can I track my order?", "Where is my package right now?", "How do I check my order status?", "Is there a way to see where my delivery is?"],
    "cancel_order": ["How do I cancel my order?", "Can I cancel an order I just placed?", "I want to cancel my purchase, what do I do?", "Is it possible to cancel my order before it ships?"],
    "return_policy": ["What is your return policy?", "How many days do I have to return an item?", "Can I return a product if I don't like it?", "Tell me about returns."],
    "refund_time": ["How long does a refund take?", "When will I get my money back after a return?", "How many days for the refund to reach my account?", "Refund timeline?"],
    "payment_methods": ["What payment methods do you accept?", "Can I pay with UPI?", "Which ways can I pay on ShopEasy?", "Do you accept credit cards and net banking?"],
    "cod": ["Do you offer cash on delivery?", "Is COD available?", "Can I pay cash when the order arrives?", "Is cash on delivery an option?"],
    "delivery_time": ["How long does delivery take?", "How many days will shipping take?", "When will my order arrive usually?", "What is the normal delivery time?"],
    "shipping_cost": ["Is shipping free?", "How much do you charge for delivery?", "What are the shipping charges?", "Do I have to pay for delivery?"],
    "intl_shipping": ["Do you ship internationally?", "Can you deliver outside India?", "Do you ship to the USA?", "Is international delivery available?"],
    "change_address": ["How do I change my delivery address?", "Can I update the shipping address after ordering?", "I entered the wrong address, how do I fix it?", "Change address for my order?"],
    "contact_support": ["How do I contact customer support?", "What is your customer care number?", "How can I talk to a human agent?", "How do I reach support?"],
    "support_hours": ["What are your support hours?", "When is customer support available?", "Is support open on weekends?", "What time does customer care open?"],
    "damaged_item": ["My item arrived damaged, what should I do?", "I received a broken product.", "The package was damaged on delivery, help.", "Product came broken, how do I get a replacement?"],
    "wrong_item": ["I received the wrong item.", "You sent me a different product than I ordered.", "Wrong product delivered, what now?", "The item I got is not what I ordered."],
    "exchange": ["Can I exchange a product for a different size?", "How do I exchange shoes for another size?", "Is size exchange possible?", "I need a different size, can I swap it?"],
    "warranty": ["Do products come with a warranty?", "How do I claim warranty on an electronic item?", "Is there a warranty on phones bought here?", "Warranty claim process?"],
    "invoice": ["How do I download my invoice?", "Where can I find the GST invoice for my order?", "I need a bill for my purchase.", "How to get an invoice copy?"],
    "coupon": ["How do I apply a coupon code?", "Where do I enter a promo code?", "My discount code is not working.", "How do coupons work at checkout?"],
    "account_delete": ["How do I delete my account?", "I want to close my ShopEasy account.", "Can you remove my account and data?", "Account deletion steps?"],
    "create_account": ["How do I create an account?", "How can I sign up on ShopEasy?", "Do I need an account to order?", "Registration process?"],
    "emi": ["Do you offer EMI?", "Can I pay in monthly installments?", "Is no-cost EMI available?", "How does EMI work on ShopEasy?"],
    "gift_wrap": ["Do you offer gift wrapping?", "Can I send an order as a gift?", "Is gift wrap available?", "Can I add a gift message?"],
    "out_of_stock": ["When will an out-of-stock item be available again?", "How do I get notified when a product is back in stock?", "Item is sold out, will it restock?", "Restock alerts?"],
    "order_not_received": ["My order shows delivered but I didn't get it.", "Marked as delivered, but nothing arrived.", "I haven't received my package although it says delivered.", "Order delivered status but no parcel."],
    "membership": ["What is ShopEasy Plus membership?", "What benefits does the Plus membership give?", "Is Plus membership worth it?", "How much does Plus cost?"],
    "seller": ["How can I become a seller on ShopEasy?", "I want to sell my products on your site.", "Seller registration?", "How do I list my products on ShopEasy?"],
    "bulk_order": ["Do you accept bulk orders?", "Can I place a corporate order?", "I need 200 units, is there a bulk discount?", "Bulk purchase options?"],
    "price_drop": ["The price dropped after I bought it, can I get the difference?", "Do you have price protection?", "Price reduced a day after my purchase, refund difference?", "Price match policy?"],
    "secure_payment": ["Is it safe to pay on ShopEasy?", "Are my card details secure?", "Do you store my card information?", "How secure is payment on your site?"],
    "otp": ["I'm not receiving the OTP.", "OTP not coming to my phone.", "Login OTP not received, help.", "Why am I not getting the verification code?"],
    "change_phone": ["How do I change my registered mobile number?", "Update phone number on my account?", "I have a new number, how do I change it?", "Change mobile number in profile?"],
    "wishlist": ["How do I add items to my wishlist?", "Where is my wishlist?", "Can I save products for later?", "How does the wishlist work?"],
    "reviews": ["How do I write a product review?", "Can I review something I bought?", "Where do I leave a rating?", "How to post a review?"],
    "replacement_time": ["How long does a replacement take?", "When will I get my replacement item?", "Replacement delivery time?", "How many days for a replacement?"],
    "pincode": ["Do you deliver to my pincode?", "How do I check if delivery is available in my area?", "Is my location serviceable?", "Check delivery availability for a pincode?"],
    "express": ["Do you have same-day delivery?", "Is express shipping available?", "Can I get my order tomorrow?", "Fast delivery options?"],
    "order_history": ["Where can I see my past orders?", "How do I view my order history?", "Show me my previous purchases.", "Order history location?"],
    "multiple_addresses": ["Can I save multiple addresses?", "How do I add a second delivery address?", "Manage saved addresses?", "Add a new address to my account?"],
    "partial_delivery": ["Only part of my order arrived.", "Some items are missing from my order.", "I received only one of two items.", "Partial delivery, where's the rest?"],
    "refund_method": ["Where will my refund be credited?", "Will the refund go back to my UPI?", "Can I get the refund as store credit?", "Refund to original payment method?"],
    "student_discount": ["Do you have a student discount?", "Any offers for college students?", "Student offers available?", "Is there a discount for students?"],
    "festival_sale": ["When is the next big sale?", "When does the Diwali sale start?", "Upcoming sale dates?", "Is there a festive sale coming?"],
    "size_guide": ["How do I find my size?", "Where is the size chart?", "Size guide for shirts?", "How do I know which size to order?"],
    "data_privacy": ["How do you use my personal data?", "Do you sell my data?", "What is your privacy policy?", "Is my information shared with third parties?"],
}

EASY = [
    "Translate 'thank you' to Hindi.", "Translate 'good morning' to Kannada.", "Say hello in Tamil.", "What does GST stand for?",
    "What does UPI stand for?", "Define 'invoice' in one line.", "What is the plural of 'parcel'?", "Thanks, that's all!",
    "Hi!", "Good evening.", "What's the opposite of 'refund'?", "Convert 10 km to miles.", "What is 15% of 2000?",
    "Spell 'delivery' backwards.", "Give me a synonym for 'quick'.", "Is 1999 an odd number?", "What day comes after Friday?",
    "Write 'order confirmed' in title case.", "What is the capital of Karnataka?", "Translate 'where is my order' to Hindi.",
    "Ok thanks", "Bye", "What does EMI stand for?", "What is a pincode?", "Define 'courier'.",
]

HARD = [
    "I ordered a laptop 12 days ago, it arrived with a cracked screen, the replacement was cancelled without reason, and support stopped replying. Write a firm but polite complaint email that lists the timeline and asks for a full refund or replacement within 7 days.",
    "Compare buying a ₹60,000 phone with no-cost EMI over 9 months versus paying upfront with a 7% instant discount. Which is cheaper, and by how much? Show the calculation.",
    "I run a small business and want to buy 150 office chairs. Draft a step-by-step plan to evaluate sellers, negotiate a bulk price, and manage delivery and installation risks.",
    "Explain step by step how an online store should design its return and refund system so refunds are fast but fraud is low. Include trade-offs.",
    "Write a Python function that takes a list of orders (id, amount, status) and returns the total refunded amount per day, with type hints and two unit tests.",
    "My order of 3 items was split into 2 shipments; one was delivered, one is stuck for 9 days, and the app shows contradictory statuses. Analyze what probably went wrong and what I should do in order.",
    "Design a loyalty points program for an e-commerce site: how points are earned, redeemed, expire, and how to prevent abuse. Justify each rule.",
    "Write an SQL query that finds customers who placed more than 3 orders in the last 30 days but never left a review, and explain how to index the tables for it.",
    "A product costs ₹1,499, has a 20% discount, then a ₹200 coupon, then 18% GST is applied on the final price. What do I pay? Explain each step and whether the order of discounts matters.",
    "Write a 250-word product description for noise-cancelling headphones aimed at college students, with a headline, 3 benefit bullets, and a call to action, without exaggerated claims.",
    "Analyze the pros and cons of cash on delivery for an online store in India and propose a policy that keeps COD but reduces fake orders.",
    "Plan a 7-day budget meal kit order for a family of four under ₹3,000 with vegetarian options, and list it as a shopping list grouped by category.",
    "Debug this JavaScript that should calculate a cart total but returns NaN: function total(items){ let t; items.forEach(i => t += i.price * i.qty); return t; } Explain the bug and fix it.",
    "Explain the difference between a refund, a replacement and store credit, and recommend which a customer should choose in three different situations.",
    "Draft a polite message in both English and Hindi informing customers that deliveries will be delayed by 2 days due to heavy rain, and offering a 10% coupon.",
]


def build(n: int = 1000) -> list[dict]:
    intents = list(FAQ)
    random.shuffle(intents)
    weights = [1 / (i + 1) ** 0.9 for i in range(len(intents))]  # Zipf: a few questions are very popular
    rows = []
    for i in range(n):
        r = random.random()
        if r < 0.70:
            intent = random.choices(intents, weights)[0]
            text = random.choice(FAQ[intent])
            if random.random() < 0.15:  # people type the same thing sloppily
                text = text.lower().rstrip("?.!")
            rows.append({"id": i, "kind": "faq", "intent": intent, "text": text})
        elif r < 0.85:
            rows.append({"id": i, "kind": "easy", "intent": "general", "text": random.choice(EASY)})
        else:
            rows.append({"id": i, "kind": "hard", "intent": "complex", "text": random.choice(HARD)})
    return rows


if __name__ == "__main__":
    rows = build()
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "system": SYSTEM}, ensure_ascii=False) + "\n")
    uniq = len({r["text"] for r in rows})
    print(f"wrote {len(rows)} prompts ({uniq} unique texts) -> {OUT}")
    for k in ("faq", "easy", "hard"):
        print(f"  {k}: {sum(r['kind'] == k for r in rows)}")
