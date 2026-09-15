"""
Script to import AP Psychology Chapter 3 Biological Bases of Behavior (Task 2) words.
"""
from vocab.db import Database

TASK2_WORDS = [
    # --- Endocrine System ---
    {
        "word": "Endocrine system",
        "pos": "noun",
        "phonetic": "/ˈen.də.krɪn ˈsɪs.təm/",
        "definition": "内分泌系统 (Glandular communication network that secretes hormones directly into the bloodstream)",
        "example": "The endocrine system works alongside the nervous system to coordinate metabolism, growth, and stress responses.",
        "mnemonic": "Endo = internal; secretes hormones inside the bloodstream slowly like radio broadcasts.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "hormone",
        "pos": "noun",
        "phonetic": "/ˈhɔːr.moʊn/",
        "definition": "激素 (Chemical messengers manufactured by endocrine glands that travel through the bloodstream)",
        "example": "Hormones regulate physiological processes including hunger, sleep, mood, and reproduction.",
        "mnemonic": "Hormones rush into the blood to set the body in motion.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "hypothalamus",
        "pos": "noun",
        "phonetic": "/ˌhaɪ.poʊˈθæl.ə.məs/",
        "definition": "下丘脑 (Brain structure below thalamus governing maintenance activities: the 4 F's — fighting, fleeing, feeding, and mating)",
        "example": "The hypothalamus signals the pituitary gland to trigger endocrine responses during stress.",
        "mnemonic": "Hypo (below) the thalamus; controls the 4 Fs: Feeding, Fleeing, Fighting, and Fornicating.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system, Limbic system"
    },
    {
        "word": "pituitary gland",
        "pos": "noun",
        "phonetic": "/pɪˈtjuː.ɪ.tər.i ɡlænd/",
        "definition": "垂体 (The endocrine system's master gland that under hypothalamus control regulates growth and other glands)",
        "example": "The pituitary gland secretes growth hormone and triggers puberty.",
        "mnemonic": "Pit boss / master of all endocrine glands.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "growth hormone",
        "pos": "noun",
        "phonetic": "/ɡroʊθ ˈhɔːr.moʊn/",
        "definition": "生长激素 (Anterior pituitary hormone that stimulates somatic growth and cellular reproduction)",
        "example": "An oversecretion of growth hormone during childhood causes gigantism, while undersecretion causes dwarfism.",
        "mnemonic": "GH directly fuels physical Growth and Height.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "adrenal gland",
        "pos": "noun",
        "phonetic": "/əˈdriː.nəl ɡlænd/",
        "definition": "肾上腺 (Pair of endocrine glands situated above kidneys that secrete epinephrine and norepinephrine in stress)",
        "example": "During a flight-or-fight emergency, the adrenal glands release adrenaline to surge blood sugar and heart rate.",
        "mnemonic": "Ad-renal: adjacent to the renal (kidneys).",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "adrenaline/epinephrine",
        "pos": "noun",
        "phonetic": "/əˈdren.əl.ɪn / ˌep.əˈnef.rɪn/",
        "definition": "肾上腺素 (Hormone secreted by adrenal medulla that increases cardiac output and raises glucose levels in emergencies)",
        "example": "The sight of the oncoming truck triggered an adrenaline rush, preparing her to jump out of the way.",
        "mnemonic": "Epi (above) + nephros (kidney) -> adrenaline powers the fight-or-flight burst.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "testosterone",
        "pos": "noun",
        "phonetic": "/tesˈtɒs.tər.oʊn/",
        "definition": "睾酮 (Primary male sex hormone produced in testes and adrenals stimulating male sexual traits and aggression)",
        "example": "Higher levels of testosterone have been correlated with risk-taking and competitive behavior.",
        "mnemonic": "Testes -> testosterone.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "oxytocin",
        "pos": "noun",
        "phonetic": "/ˌɑːk.sɪˈtoʊ.sɪn/",
        "definition": "催产素 (Pituitary hormone facilitating social bonding, maternal attachment, empathy, and uterine contractions)",
        "example": "Oxytocin, often called the 'cuddle hormone', promotes trust between mother and infant during nursing.",
        "mnemonic": "Oxy-TOC-in: Touch, Oxy, Caring — the love and social bonding hormone.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "pineal gland",
        "pos": "noun",
        "phonetic": "/ˈpaɪ.ni.əl ɡlænd/",
        "definition": "松果体 (Small endocrine gland in the brain producing melatonin to modulate sleep-wake circadian cycles)",
        "example": "The pineal gland responds to darkness by increasing melatonin synthesis.",
        "mnemonic": "Pinecone-shaped gland in the center of the brain controlling night sleep.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },
    {
        "word": "melatonin",
        "pos": "noun",
        "phonetic": "/ˌmel.əˈtoʊ.nɪn/",
        "definition": "褪黑激素 (Pineal hormone regulating sleep-wake circadian cycles; rises in darkness, drops in light)",
        "example": "Exposure to blue screen light before bedtime suppresses melatonin, causing insomnia.",
        "mnemonic": "Mellow-tonin makes you mellow and sleepy when the lights go down.",
        "tags": "AP Psychology, Ch3 Biological Bases, Endocrine system"
    },

    # --- Nervous System ---
    {
        "word": "Nervous system",
        "pos": "noun",
        "phonetic": "/ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "神经系统 (The body's speedy, electrochemical communication network comprising all nerve cells)",
        "example": "The nervous system processes sensory information and transmits motor commands in milliseconds.",
        "mnemonic": "The electrical wiring grid of the human body.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "central nervous system (CNS)",
        "pos": "noun",
        "phonetic": "/ˈsen.trəl ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "中枢神经系统 (The core decision-making division of the nervous system consisting of the brain and spinal cord)",
        "example": "The CNS coordinates high-level cognitive processes, sensory perception, and motor coordination.",
        "mnemonic": "Central command center: Head (brain) and Backbone (spinal cord).",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "brain",
        "pos": "noun",
        "phonetic": "/breɪn/",
        "definition": "脑 (The primary organ of the central nervous system coordinating thought, emotion, sensory perception, and action)",
        "example": "The brain contains approximately 86 billion neurons communicating through trillions of synapses.",
        "mnemonic": "The supreme master computer of mind and behavior.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system, Brain"
    },
    {
        "word": "spinal cord",
        "pos": "noun",
        "phonetic": "/ˈspaɪ.nəl kɔːrd/",
        "definition": "脊髓 (Thick column of neural tissue connecting brain to peripheral nerves and mediating simple reflexes)",
        "example": "The knee-jerk reflex is mediated directly by interneurons in the spinal cord without brain intervention.",
        "mnemonic": "The information highway running down the spine.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "peripheral nervous system (PNS)",
        "pos": "noun",
        "phonetic": "/pəˈrɪf.ər.əl ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "外周神经系统 (Sensory and motor neurons connecting the central nervous system to the rest of the body)",
        "example": "The PNS branches outward into somatic and autonomic systems.",
        "mnemonic": "Peripheral = on the outer edge, reaching hands, feet, and internal organs.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "somatic nervous system",
        "pos": "noun",
        "phonetic": "/soʊˈmæt.ɪk ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "躯体神经系统 (Subdivision of PNS controlling voluntary movements of skeletal muscles and relaying sensory input)",
        "example": "Deciding to wave your hand relies on motor neurons in the somatic nervous system.",
        "mnemonic": "Soma = body; voluntary bodily muscle actions.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "autonomic nervous system (ANS)",
        "pos": "noun",
        "phonetic": "/ˌɔː.təˈnɑː.mɪk ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "自主神经系统 (Subdivision of PNS regulating involuntary vegetative processes: glands, heart rate, digestion)",
        "example": "The ANS maintains homeostasis automatically, regulating heartbeat and pupil dilation without conscious effort.",
        "mnemonic": "Automatic / Autonomic: operates on autopilot.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "sympathetic nervous system (SNS)",
        "pos": "noun",
        "phonetic": "/ˌsɪm.pəˈθet.ɪk ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "交感神经系统 (Division of ANS that mobilizes energy in stressful situations; the fight-or-flight system)",
        "example": "When you encounter a snake on a trail, your sympathetic nervous system accelerates your heart and dilates pupils.",
        "mnemonic": "Has 'sympathy' for you when you are in danger: powers up Fight or Flight!",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },
    {
        "word": "parasympathetic nervous system (PNS)",
        "pos": "noun",
        "phonetic": "/ˌpær.əˌsɪm.pəˈθet.ɪk ˈnɜːr.vəs ˈsɪs.təm/",
        "definition": "副交感神经系统 (Division of ANS that calms the body to conserve energy; the rest-and-digest system)",
        "example": "After the danger passes, the parasympathetic nervous system slows heart rate and stimulates digestion.",
        "mnemonic": "Para-parachute / Peace: restores peace, Rest & Digest.",
        "tags": "AP Psychology, Ch3 Biological Bases, Nervous system"
    },

    # --- Brain ---
    {
        "word": "brainstem",
        "pos": "noun",
        "phonetic": "/ˈbreɪn.stem/",
        "definition": "脑干 (Oldest evolutionary brain region; controls automatic survival functions like breathing, heartbeat, and blood pressure)",
        "example": "Damage to the brainstem is often fatal because it regulates involuntary vital functions.",
        "mnemonic": "The stem that holds up the flower; without the stem, the whole brain dies.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "medulla",
        "pos": "noun",
        "phonetic": "/məˈdʌl.ə/",
        "definition": "延髓 (Base of brainstem controlling heartbeat, respiration, swallowing, and vomiting reflexes)",
        "example": "The medulla keeps you breathing automatically even when in deep unconscious sleep.",
        "mnemonic": "Med-medal: wearing a medal over your heart and lungs (controls heartbeat & breathing).",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "pons",
        "pos": "noun",
        "phonetic": "/pɒnz/",
        "definition": "脑桥 (Structure above medulla that acts as a bridge coordinating movement, facial expressions, and sleep/dream states)",
        "example": "The pons contains nuclei that initiate REM sleep and suppress muscle activity during dreaming.",
        "mnemonic": "Pons = French for bridge (pont) / pond: relax near the pond for sleep, dreams, and coordination.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "midbrain",
        "pos": "noun",
        "phonetic": "/ˈmɪd.breɪn/",
        "definition": "中脑 (Segment of brainstem between pons and diencephalon integrating sensory information with motor output and dopamine production)",
        "example": "The substantia nigra in the midbrain produces dopamine crucial for smooth voluntary movement.",
        "mnemonic": "In the middle of the brainstem, routing visual and auditory orientation reflexes.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "reticular formation",
        "pos": "noun",
        "phonetic": "/rɪˈtɪk.jə.lər fɔːrˈmeɪ.ʃən/",
        "definition": "网状结构 (Nerve network traveling through brainstem that plays a central role in controlling alertness and arousal)",
        "example": "If the reticular formation is severed, an animal lapses into an irreversible coma.",
        "mnemonic": "Re-Tickle-ar: tickle me awake; controls arousal and waking up.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "diencephalon",
        "pos": "noun",
        "phonetic": "/ˌdaɪ.enˈsef.ə.lɒn/",
        "definition": "间脑 (Forebrain division between cerebrum and midbrain containing the thalamus and hypothalamus)",
        "example": "The diencephalon acts as the primary relay and endocrine regulation center of the central nervous system.",
        "mnemonic": "Di = two (Thalamus and Hypothalamus).",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "thalamus",
        "pos": "noun",
        "phonetic": "/ˈθæl.ə.məs/",
        "definition": "丘脑 (The brain's sensory switchboard atop the brainstem; directs all incoming sensory signals except smell to the cortex)",
        "example": "Visual signals from the retina pass through the lateral geniculate nucleus of the thalamus before reaching the occipital lobe.",
        "mnemonic": "Hal & Amos: traffic cops directing all sensory traffic (except smell!).",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "cerebellum",
        "pos": "noun",
        "phonetic": "/ˌser.əˈbel.əm/",
        "definition": "小脑 (The 'little brain' at the rear of brainstem; processes sensory input, coordinates balance, posture, and procedural motor memory)",
        "example": "Alcohol consumption impairs cerebellum function, resulting in slurred speech and loss of equilibrium.",
        "mnemonic": "Cere-BELL-um: like a ballerina balancing on a tightrope; bell ringer balance.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "limbic system",
        "pos": "noun",
        "phonetic": "/ˈlɪm.bɪk ˈsɪs.təm/",
        "definition": "边缘系统 (Neural system located below cerebral hemispheres associated with emotions, drives, and memory; includes amygdala, hippocampus, hypothalamus)",
        "example": "The limbic system bridges primitive brainstem reflexes with advanced cortical deliberation.",
        "mnemonic": "Hungry, angry, emotional, and remembering: HAH (Hippocampus, Amygdala, Hypothalamus).",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain, Limbic system"
    },
    {
        "word": "amygdala",
        "pos": "noun",
        "phonetic": "/əˈmɪɡ.də.lə/",
        "definition": "杏仁核 (Two almond-shaped neural clusters in the limbic system linked to emotional processing, particularly fear and aggression)",
        "example": "Damage to the amygdala in monkeys produces Kluver-Bucy syndrome, characterized by a lack of fear.",
        "mnemonic": "Amygdala sounds like 'Amy G. Dala' — a scary monster triggering panic and anger; almond-shaped.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain, Limbic system"
    },
    {
        "word": "hippocampus",
        "pos": "noun",
        "phonetic": "/ˌhɪp.əˈkæm.pəs/",
        "definition": "海马 (Curved neural structure in limbic system essential for consolidating new explicit memories into long-term storage)",
        "example": "Patient H.M. lost his hippocampus and could no longer form new episodic memories, while retaining older ones.",
        "mnemonic": "Hippo on campus: if you saw a hippo walking on your campus, you would definitely remember it!",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain, Limbic system"
    },
    {
        "word": "cerebrum",
        "pos": "noun",
        "phonetic": "/səˈriː.brəm/",
        "definition": "大脑 (The largest part of the human brain comprising two cerebral hemispheres responsible for thought, language, and perception)",
        "example": "The cerebrum enables complex decision making, creative reasoning, and conscious experience.",
        "mnemonic": "Cerebrum = the big thinking brain.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "cerebral cortex",
        "pos": "noun",
        "phonetic": "/səˈriː.brəl ˈkɔːr.teks/",
        "definition": "大脑皮层 (The intricate, wrinkled outer layer of gray matter covering cerebral hemispheres; the body's ultimate control and information-processing center)",
        "example": "The convoluted folding of the cerebral cortex dramatically increases its surface area inside the cranium.",
        "mnemonic": "Cortex = bark of a tree: the wrinkled outer bark of the brain.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "frontal lobes",
        "pos": "noun",
        "phonetic": "/ˈfrʌn.təl loʊbz/",
        "definition": "额叶 (Portion of cerebral cortex behind forehead involved in speaking, muscle movement, planning, judgement, and impulse control)",
        "example": "Phineas Gage suffered damage to his frontal lobes, dramatically altering his personality and social restraint.",
        "mnemonic": "At the front of your head: the CEO of the brain, making plans and decisions.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "parietal lobes",
        "pos": "noun",
        "phonetic": "/pəˈraɪ.ə.təl loʊbz/",
        "definition": "顶叶 (Cortex region at top-rear of head containing somatosensory cortex; processes touch, body position, and spatial orientation)",
        "example": "The somatosensory strip in the parietal lobes registers sensations of warmth, pressure, and pain.",
        "mnemonic": "Parietal = Piranha bites you on the top of the head; you feel the touch and bite.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "occipital lobes",
        "pos": "noun",
        "phonetic": "/ɒkˈsɪp.ɪ.təl loʊbz/",
        "definition": "枕叶 (Cortex region at the back of head containing visual cortex; processes visual information)",
        "example": "A blow to the occipital lobes can cause temporary blindness or seeing stars.",
        "mnemonic": "Occipital = Optical / Octopus with eyes on the back of its head.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "temporal lobes",
        "pos": "noun",
        "phonetic": "/ˈtem.pər.əl loʊbz/",
        "definition": "颞叶 (Cortex region above the ears containing auditory cortex and Wernicke's area; processes hearing, speech comprehension, and face recognition)",
        "example": "The primary auditory cortex in the temporal lobes decodes musical pitch and speech sounds.",
        "mnemonic": "Near your temples and ears: Tempo (music/hearing) and Tone.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "cerebral hemisphere",
        "pos": "noun",
        "phonetic": "/səˈriː.brəl ˈhem.ɪ.sfɪər/",
        "definition": "大脑半球 (The left and right symmetrical halves of the cerebrum, each specialized for distinct cognitive functions)",
        "example": "In most people, the left cerebral hemisphere is specialized for language, while the right handles spatial perception.",
        "mnemonic": "Half of the spherical cerebrum.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },
    {
        "word": "corpus callosum",
        "pos": "noun",
        "phonetic": "/ˌkɔːr.pəs kəˈloʊ.səm/",
        "definition": "胼胝体 (The wide band of axon fibers connecting the left and right cerebral hemispheres, facilitating interhemispheric communication)",
        "example": "In split-brain surgery, the corpus callosum is severed to prevent severe epileptic seizures from spreading.",
        "mnemonic": "Corpus Call-Someone: the phone cable calling between left and right hemispheres.",
        "tags": "AP Psychology, Ch3 Biological Bases, Brain"
    },

    # --- Neuron ---
    {
        "word": "Neuron",
        "pos": "noun",
        "phonetic": "/ˈnjʊə.rɒn/",
        "definition": "神经元 (A nerve cell; the fundamental building block of the nervous system specialized for electrochemical signaling)",
        "example": "Each sensory neuron transmits environmental impulses toward the spinal cord and brain.",
        "mnemonic": "The single micro-transistor and communicator of the brain.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "dendrite",
        "pos": "noun",
        "phonetic": "/ˈden.draɪt/",
        "definition": "树突 (Bushy, branching extensions of a neuron that receive chemical messages and conduct impulses toward the cell body)",
        "example": "Dendrites possess numerous synaptic receptors where neurotransmitters bind.",
        "mnemonic": "Dendrites Deliver: tree branches reaching out to listen to neighbors.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "axon",
        "pos": "noun",
        "phonetic": "/ˈæk.sɒn/",
        "definition": "轴突 (Long fiber of a neuron through which neural electrical impulses pass to terminal branches to communicate with other cells)",
        "example": "Some motor axons extend over a meter from the lower spine down to the muscles in the foot.",
        "mnemonic": "Axon = Away: sends messages Away from the cell body.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "soma/cell body",
        "pos": "noun",
        "phonetic": "/ˈsoʊ.mə / sel ˈbɒd.i/",
        "definition": "胞体 (The metabolic life-support center of a neuron containing the nucleus and sustaining cell health)",
        "example": "The soma integrates incoming electrical potentials from all dendrites before firing.",
        "mnemonic": "Soma = body: the core body keeping the neuron alive.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "myelin sheath",
        "pos": "noun",
        "phonetic": "/ˈmaɪ.ə.lɪn ʃiːθ/",
        "definition": "髓鞘 (Layer of fatty tissue encasing the axon that dramatically speeds up neural impulse transmission via saltatory conduction)",
        "example": "Multiple sclerosis results from the progressive degeneration of the myelin sheath, causing communication breakdown.",
        "mnemonic": "Plastic insulation around an electrical cord; speeds up the signal.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "synapse",
        "pos": "noun",
        "phonetic": "/ˈsɪn.æps/",
        "definition": "突触 (The microscopic junction between the axon terminal of the sending neuron and the dendrite or cell body of the receiving neuron)",
        "example": "Neurotransmitters diffuse across the synaptic gap in less than a millisecond.",
        "mnemonic": "The tiny gap where neurons snap/chat with chemicals.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },
    {
        "word": "nerves",
        "pos": "noun",
        "phonetic": "/nɜːrvz/",
        "definition": "神经 (Bundled cables formed by many axons connecting the central nervous system with muscles, glands, and sensory organs)",
        "example": "The optic nerve carries over a million axon fibers from the retina to the thalamus.",
        "mnemonic": "Heavy multi-strand cables carrying biological data.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neuron"
    },

    # --- Neurotransmission ---
    {
        "word": "Neurotransmission",
        "pos": "noun",
        "phonetic": "/ˌnjʊə.roʊ.trænzˈmɪʃ.ən/",
        "definition": "神经传导 (The electrochemical process by which signaling molecules are released by axon terminals to bind to receptors on adjacent cells)",
        "example": "Psychoactive medications act primarily by altering steps in synaptic neurotransmission.",
        "mnemonic": "Sending electrical and chemical signals across the synapse.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "neural impulse",
        "pos": "noun",
        "phonetic": "/ˈnjʊə.rəl ˈɪm.pʌls/",
        "definition": "神经冲动 (An action potential; a brief electrical charge that travels down an axon generated by the movement of positively charged ions)",
        "example": "A neural impulse operates on an all-or-none principle: it fires completely or not at all.",
        "mnemonic": "The spark of electricity rushing down the axon wire.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "neurotransmitter",
        "pos": "noun",
        "phonetic": "/ˌnjʊə.roʊ.trænzˈmɪt.ər/",
        "definition": "神经递质 (Chemical messengers released across the synaptic cleft that bind to receptor sites on receiving neurons)",
        "example": "Dopamine and serotonin are crucial neurotransmitters influencing human affect and motivation.",
        "mnemonic": "Keys fitting into specific lock receptors on the receiving cell.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "acetylcholine",
        "pos": "noun",
        "phonetic": "/əˌsiː.təlˈkoʊ.liːn/",
        "definition": "乙酰胆碱 (Neurotransmitter enabling muscle contraction, voluntary movement, attention, and memory; deteriorates in Alzheimer's disease)",
        "example": "Curare poison blocks acetylcholine receptors, resulting in paralysis, while botulinum toxin prevents its release.",
        "mnemonic": "ACh = Action & Memory: activates muscles and memory.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "dopamine",
        "pos": "noun",
        "phonetic": "/ˈdoʊ.pə.miːn/",
        "definition": "多巴胺 (Neurotransmitter influencing movement, learning, attention, and the brain's reward/pleasure circuits)",
        "example": "Excess dopamine activity is linked to schizophrenia, while dopamine neuron loss causes tremors in Parkinson's disease.",
        "mnemonic": "DOPE = makes you feel rewarded; Dopamine drives anticipation and reward.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "serotonin",
        "pos": "noun",
        "phonetic": "/ˌser.əˈtoʊ.nɪn/",
        "definition": "5-羟色胺 (Neurotransmitter affecting mood, hunger, sleep, and arousal; undersupply strongly linked to clinical depression)",
        "example": "Selective Serotonin Reuptake Inhibitors (SSRIs) boost synaptic serotonin levels to relieve depressive symptoms.",
        "mnemonic": "Sir Rotten-mood needs Serotonin to feel bright and balanced.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "endorphin",
        "pos": "noun",
        "phonetic": "/enˈdɔːr.fɪn/",
        "definition": "内啡肽 (Natural, opiate-like neurotransmitters linked to pain alleviation and feelings of pleasure during exertion or injury)",
        "example": "The 'runner's high' is mediated by endogenous endorphin release in the central nervous system.",
        "mnemonic": "Endogenous Morphine: internal painkiller produced by the body.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "glutamate",
        "pos": "noun",
        "phonetic": "/ˈɡluː.tə.meɪt/",
        "definition": "谷氨酸盐 (The primary excitatory neurotransmitter in the brain involved in memory; oversupply can overstimulate brain producing migraines or seizures)",
        "example": "Excess glutamate release following a stroke contributes to excitotoxicity and cellular death.",
        "mnemonic": "Glut-ton of Excitement: gluing memories together, excitatory!",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "norepinephrine",
        "pos": "noun",
        "phonetic": "/ˌnɔːr.ep.əˈnef.rɪn/",
        "definition": "去甲肾上腺素 (Neurotransmitter and hormone that helps control alertness and physical arousal; undersupply can depress mood)",
        "example": "Norepinephrine constricts blood vessels and sharpens concentration during stressful encounters.",
        "mnemonic": "No-Re-pining: keeps you alert and energized in danger.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    },
    {
        "word": "GABA",
        "pos": "noun",
        "phonetic": "/ˈɡæb.ə/",
        "definition": "γ-氨基丁酸 (The primary inhibitory neurotransmitter in the brain; undersupply linked to seizures, tremors, and anxiety)",
        "example": "Anti-anxiety medications like benzodiazepines enhance GABA receptor sensitivity to calm nervous activity.",
        "mnemonic": "GABA = Get A Break Already: brakes of the brain, puts a stop to runaway firing.",
        "tags": "AP Psychology, Ch3 Biological Bases, Neurotransmission"
    }
]


def import_task2(db_path: str = "vocab_data.db"):
    db = Database(db_path)
    group_name = "AP Psychology: Biological Bases (Task 2)"
    existing_group = db.get_group_by_name(group_name)

    if existing_group:
        gid = existing_group.id
        print(f"Using existing group: '{group_name}' (id={gid})")
    else:
        gid = db.create_group(
            name=group_name,
            description="Summer HW Task 2: Terminologies related to biological bases of behavior (Psychology and Life Ch3).",
            color="magenta"
        )
        print(f"Created group: '{group_name}' (id={gid})")

    existing_words = {w.word.lower(): w for w in db.get_words(group_id=gid, limit=500)}
    added = 0
    updated = 0

    for item in TASK2_WORDS:
        word_key = item["word"].lower()
        if word_key in existing_words:
            # Update with full definition
            w = existing_words[word_key]
            w.definition = item["definition"]
            w.phonetic = item["phonetic"]
            w.pos = item["pos"]
            w.example = item["example"]
            w.mnemonic = item["mnemonic"]
            w.tags = item["tags"]
            db.update_word(w)
            updated += 1
        else:
            db.add_word(
                group_id=gid,
                word=item["word"],
                definition=item["definition"],
                phonetic=item["phonetic"],
                pos=item["pos"],
                example=item["example"],
                mnemonic=item["mnemonic"],
                tags=item["tags"]
            )
            added += 1

    print(f"Import complete! Added {added} new words, updated {updated} words.")
    total = len(db.get_words(group_id=gid, limit=500))
    print(f"Total words in '{group_name}': {total}")


if __name__ == "__main__":
    import_task2()
