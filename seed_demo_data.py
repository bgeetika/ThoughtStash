"""Seed realistic Bay Area demo data spanning the last 40 days across Tech, Work, and Family."""

import asyncio
import json
import os
from datetime import datetime

import agents
import db

DEMO_THOUGHTS = [
    {
        "created_at": "2026-07-14T07:45:00Z",
        "transcript": "Why do all AI memory systems assume memory is just a vector database of documents? Real human memory is episodic and tied to emotional state and location. If we want personal agents to actually understand us over months, we need to capture what we're actively thinking out loud during walks, not just our email inbox.",
        "summary": "Reflections on why existing AI memory architectures fail by ignoring episodic, human-curated streams of consciousness.",
        "topics": ["AI agents", "episodic memory", "cognitive architecture", "long-horizon"],
        "entities": ["Vector DBs", "Personal Agents"],
        "mood": "inspired",
        "key_insights": ["Episodic, voice-captured thoughts provide higher signal than passive document indexing for long-horizon AI."],
        "thought_type": "idea",
        "urgency": "medium",
        "implicit_questions": ["How can episodic memory be modeled beyond basic RAG?", "What role does emotional state play in agent recall?"],
        "latitude": 37.4205,
        "longitude": -122.1830,
        "location_name": "Stanford Dish Trail, Palo Alto, CA"
    },
    {
        "created_at": "2026-07-18T18:30:00Z",
        "transcript": "Looking at our team sprint velocity... we're spending almost 15 hours a week in status syncs and fragmented meetings. Context switching is killing our deep work time. I think I'm going to propose 'No-Meeting Thursdays' to leadership next week to give the team dedicated flow blocks.",
        "summary": "Observing team burnout from meeting fragmentation and planning to propose a dedicated deep-work day.",
        "topics": ["team velocity", "workplace productivity", "deep work", "engineering culture"],
        "entities": ["Engineering Team", "Leadership"],
        "mood": "determined",
        "key_insights": ["Fragmented calendars are directly eroding engineering deep work blocks.", "Proposing a dedicated No-Meeting day could restore focus."],
        "thought_type": "decision",
        "urgency": "high",
        "implicit_questions": ["Will leadership support a dedicated No-Meeting day?", "How to measure focus time improvement?"],
        "latitude": 37.4323,
        "longitude": -122.0880,
        "location_name": "Shoreline Park, Mountain View, CA"
    },
    {
        "created_at": "2026-07-22T20:15:00Z",
        "transcript": "Mom called earlier about their 40th anniversary trip in August. They really want to see the California coast, but Mom doesn't do well with steep winding roads. Need to find a gentle scenic route down Highway 1 toward Monterey and Carmel with easy beach walks.",
        "summary": "Brainstorming family vacation itinerary for parents' upcoming 40th anniversary visit with accessible coastal walks.",
        "topics": ["family", "parents visit", "vacation planning", "California coast"],
        "entities": ["Mom", "Monterey", "Carmel", "Highway 1"],
        "mood": "warm",
        "key_insights": ["Plan gentle, non-mountainous coastal drives and accessible walking routes for parents."],
        "thought_type": "reflection",
        "urgency": "medium",
        "implicit_questions": ["What are the best gentle coastal trails in Monterey/Carmel?", "Where to book an ocean-view anniversary dinner?"],
        "latitude": 37.3941,
        "longitude": -122.0792,
        "location_name": "Castro St, Mountain View, CA"
    },
    {
        "created_at": "2026-07-27T12:45:00Z",
        "transcript": "While walking after lunch: on-device small models could do real-time voice structuring directly on a wearable or phone, and then asynchronously sync compact knowledge embeddings to the cloud. That solves both latency and privacy for continuous thought logging.",
        "summary": "Architecture idea for hybrid edge-cloud voice agents using on-device SLMs for local structuring and cloud embeddings for graph linking.",
        "topics": ["edge AI", "system architecture", "small language models", "privacy"],
        "entities": ["SLMs", "Wearables", "Cloud Sync"],
        "mood": "analytical",
        "key_insights": ["Hybrid architecture splits immediate voice structuring locally while offloading graph consolidation to cloud."],
        "thought_type": "idea",
        "urgency": "low",
        "implicit_questions": ["Can a 2B parameter model reliably output strict JSON on device?", "What is the battery impact on mobile?"],
        "latitude": 37.4210,
        "longitude": -122.0750,
        "location_name": "Charleston Park, Mountain View, CA"
    },
    {
        "created_at": "2026-08-01T09:15:00Z",
        "transcript": "Second weekend morning hike in a row. Noticed my resting heart rate is down and I haven't had that 3 PM brain fog this week. Morning movement before staring at screens makes a huge difference. I should make 30-minute morning walks non-negotiable.",
        "summary": "Realizing the direct correlation between morning walks in nature and reduced daily cognitive fatigue.",
        "topics": ["mindfulness", "health habits", "hiking", "wellbeing"],
        "entities": ["Rancho San Antonio"],
        "mood": "peaceful",
        "key_insights": ["Outdoor morning walks directly eliminate afternoon cognitive fatigue and improve focus."],
        "thought_type": "reflection",
        "urgency": "low",
        "implicit_questions": ["How can I protect morning walk time against early calendar invites?"],
        "latitude": 37.3325,
        "longitude": -122.0864,
        "location_name": "Rancho San Antonio, Cupertino, CA"
    },
    {
        "created_at": "2026-08-05T18:10:00Z",
        "transcript": "Had a great 1-on-1 with Alex today. They were hesitant to take ownership of the distributed caching service redesign. We mapped out milestone boundaries together and broke the risk down. Seeing junior engineers gain confidence is by far the most rewarding part of tech lead work.",
        "summary": "Mentoring reflection on empowering a junior engineer to lead a complex infrastructure redesign.",
        "topics": ["mentorship", "leadership", "engineering growth", "delegation"],
        "entities": ["Alex", "Caching Service"],
        "mood": "fulfilled",
        "key_insights": ["Scaffolding risk into smaller milestones enables junior engineers to step up to major architectural ownership."],
        "thought_type": "observation",
        "urgency": "low",
        "implicit_questions": ["How to set up the right review checkpoints without micro-managing?"],
        "latitude": 37.4180,
        "longitude": -122.0090,
        "location_name": "Baylands Park, Sunnyvale, CA"
    },
    {
        "created_at": "2026-08-09T19:20:00Z",
        "transcript": "Looking at the Golden Gate Bridge in the fog. Thought capture apps like AudioPen and Speakwise do transcription and bullet points, but they stop there. The killer product isn't a better notepad; it's a model that connects your idea from two weeks ago in Palo Alto to what you're thinking right now in SF.",
        "summary": "Crystalizing the vision for ThoughtStash — moving beyond simple voice transcription to an active cross-temporal pattern engine.",
        "topics": ["product vision", "ThoughtStash", "AI second brain", "pattern recognition"],
        "entities": ["ThoughtStash", "AudioPen", "Speakwise", "San Francisco"],
        "mood": "excited",
        "key_insights": ["The true differentiator for voice thought capture is temporal graph linking and proactive insight generation, not transcription formatting."],
        "thought_type": "idea",
        "urgency": "high",
        "implicit_questions": ["How to present connections without overwhelming the user?", "What is the optimal threshold for proactive alerts?"],
        "latitude": 37.8055,
        "longitude": -122.4650,
        "location_name": "Crissy Field, San Francisco, CA"
    },
    {
        "created_at": "2026-08-12T20:30:00Z",
        "transcript": "Showed my 10-year-old niece how we build games with Python and prompt helpers. Her eyes lit up when the sprite moved on the screen. She asked if computers can think about their own thoughts. Kids ask the most profound philosophical questions without even trying.",
        "summary": "Wholesome evening teaching niece basic programming and reflecting on her question about machine consciousness.",
        "topics": ["family", "niece", "STEM education", "philosophy"],
        "entities": ["Python", "Niece"],
        "mood": "joyful",
        "key_insights": ["Teaching kids coding sparks deep first-principles questions about artificial intelligence and introspection."],
        "thought_type": "observation",
        "urgency": "low",
        "implicit_questions": ["What is the best curriculum to introduce kids to computational thinking in the AI era?"],
        "latitude": 37.3775,
        "longitude": -122.0300,
        "location_name": "Historic Murphy Ave, Sunnyvale, CA"
    },
    {
        "created_at": "2026-08-15T11:30:00Z",
        "transcript": "Weekend walk along the ocean. Dad's 40th anniversary dinner reservations are confirmed in Carmel for next Saturday. Managed to completely unplug from Slack for 48 hours for the first time this quarter. The sky didn't fall, and my head feels completely clear.",
        "summary": "Finalizing parents' anniversary plans and experiencing the mental clarity of a full digital detox weekend.",
        "topics": ["digital detox", "family celebration", "ocean walk", "work life balance"],
        "entities": ["Dad", "Carmel", "Pacific Coast"],
        "mood": "rejuvenated",
        "key_insights": ["True digital detachment over weekends dramatically improves strategic problem-solving capacity on Monday."],
        "thought_type": "reflection",
        "urgency": "low",
        "implicit_questions": ["How to make 48-hour weekend disconnects a regular quarterly rhythm?"],
        "latitude": 36.9530,
        "longitude": -122.0320,
        "location_name": "West Cliff Drive, Santa Cruz, CA"
    },
    {
        "created_at": "2026-08-18T18:45:00Z",
        "transcript": "Two weeks into 'No-Meeting Thursdays' and team commit volume is up 35%, and code review turnaround dropped from 2 days to 4 hours. The engineers feel in control of their calendars again. Definite win to present in our end-of-month retro.",
        "summary": "Validating the success of No-Meeting Thursdays with concrete metrics on engineer velocity and review latency.",
        "topics": ["team velocity", "sprint metrics", "No-Meeting Thursdays", "process improvement"],
        "entities": ["Engineering Team", "Sprint Retro"],
        "mood": "proud",
        "key_insights": ["Consolidating meetings resulted in a measured 35% increase in engineering output and faster code reviews."],
        "thought_type": "decision",
        "urgency": "medium",
        "implicit_questions": ["Should we expand focus blocks to Tuesday mornings as well?"],
        "latitude": 37.2405,
        "longitude": -122.0320,
        "location_name": "Villa Montalvo Trail, Saratoga, CA"
    },
    {
        "created_at": "2026-08-20T07:15:00Z",
        "transcript": "Morning coffee walk before standup. If long-horizon agents have persistent state, they shouldn't just query memory reactively; they should have dream/consolidation phases during idle cycles, linking disparate memories into higher-order abstractions just like human REM sleep.",
        "summary": "Conceptualizing an autonomous background consolidation cycle for AI memory inspired by biological sleep and memory consolidation.",
        "topics": ["long-horizon agents", "memory consolidation", "agent sleep cycles", "neuro-AI"],
        "entities": ["Long-Horizon Agents", "REM Sleep Model"],
        "mood": "fascinated",
        "key_insights": ["Autonomous memory consolidation during agent idle periods mimics biological sleep and prevents knowledge fragmentation."],
        "thought_type": "idea",
        "urgency": "medium",
        "implicit_questions": ["How frequently should the agent run offline consolidation sweeps?", "What loss function measures abstraction quality?"],
        "latitude": 37.4445,
        "longitude": -122.1610,
        "location_name": "University Ave, Palo Alto, CA"
    },
    {
        "created_at": "2026-08-21T17:30:00Z",
        "transcript": "Walking along the Embarcadero after our offsite. The execs liked the agent architecture proposal, but asked how we prevent context bloat over 6-month horizons. Hierarchical summarization plus semantic clustering is the answer. Going to write a 1-pager on Sunday.",
        "summary": "Post-offsite reflection on solving multi-month context degradation in personal AI agents through hierarchical summarization.",
        "topics": ["offsite", "executive review", "context compression", "agent architecture"],
        "entities": ["Exec Team", "Embarcadero Offsite"],
        "mood": "focused",
        "key_insights": ["Hierarchical summarization paired with spatio-temporal clustering solves long-horizon agent context bloat."],
        "thought_type": "decision",
        "urgency": "high",
        "implicit_questions": ["What is the target compression ratio for 6-month thought timelines?"],
        "latitude": 37.7955,
        "longitude": -122.3937,
        "location_name": "Embarcadero, San Francisco, CA"
    }
]


async def seed_data():
    print("🌱 Initializing DB...")
    db.init_db()

    print(f"🧠 Generating real Gemini embeddings for {len(DEMO_THOUGHTS)} sample thoughts...")
    for idx, item in enumerate(DEMO_THOUGHTS, 1):
        print(f"[{idx}/{len(DEMO_THOUGHTS)}] Embedding: {item['summary'][:50]}...")
        try:
            emb = agents.get_embedding(item["transcript"])
        except Exception as e:
            print(f"   Embedding error: {e}, using empty list")
            emb = []

        thought_record = {
            "created_at": item["created_at"],
            "audio_path": None,
            "transcript": item["transcript"],
            "summary": item["summary"],
            "topics": item["topics"],
            "entities": item["entities"],
            "mood": item["mood"],
            "key_insights": item["key_insights"],
            "thought_type": item["thought_type"],
            "urgency": item["urgency"],
            "implicit_questions": item["implicit_questions"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "location_name": item["location_name"],
            "embedding": emb,
            "raw_response": json.dumps(item),
        }
        t_id = db.save_thought(thought_record)
        print(f"   Saved thought #{t_id} ({item['location_name']})")

    print("\n✨ Generating Connector agent pattern links for thoughts...")
    all_thoughts = db.get_all_thoughts()
    
    # Run connector on a subset of thoughts to populate realistic connections
    for i in range(1, min(len(all_thoughts), 6)):
        target = all_thoughts[i]
        past = all_thoughts[i+1:]
        if past:
            try:
                print(f"🔗 Linking thought #{target['id']} against {len(past)} historical thoughts...")
                analysis = await agents.connector_analyze(target, past[:10])
                db.update_thought_connections(target["id"], json.dumps(analysis))
            except Exception as e:
                print(f"   Connector error on #{target['id']}: {e}")

    print(f"\n🎉 Successfully seeded {len(DEMO_THOUGHTS)} Bay Area demo thoughts across Tech, Work, and Family!")


if __name__ == "__main__":
    asyncio.run(seed_data())
