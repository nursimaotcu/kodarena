"""Versioned, server-owned exercises. Private cases never appear in the public API."""

PROBLEMS = {
    "pair-sum": {
        "title": "İki Sayının Toplamı",
        "difficulty": "Başlangıç",
        "statement": "Standart girdide boşlukla ayrılmış iki tam sayı verilir. Toplamlarını yazdırın.",
        "constraints": "−10⁹ ≤ a, b ≤ 10⁹",
        "version": 1,
        "starters": {
            "python": "a, b = map(int, input().split())\nprint(a + b)\n",
            "javascript": "const fs = require('fs');\nconst [a, b] = fs.readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconsole.log(a + b);\n",
        },
        "cases": [
            {"input": "4 7\n", "expected": "11\n", "public": True},
            {"input": "-9 3\n", "expected": "-6\n", "public": False},
            {"input": "0 0\n", "expected": "0\n", "public": False},
            {"input": "1000000000 1000000000\n", "expected": "2000000000\n", "public": False},
        ],
    },
    "balanced-brackets": {
        "title": "Dengeli Parantezler",
        "difficulty": "Orta",
        "statement": "Yalnızca ()[]{} karakterlerinden oluşan satırdaki parantezler doğru sırada kapanıyorsa YES, aksi halde NO yazdırın. Boş satır dengelidir.",
        "constraints": "0 ≤ satır uzunluğu ≤ 10.000",
        "version": 1,
        "starters": {
            "python": "text = input()\n# Yığın kullanarak parantezleri kontrol edin.\nprint('YES')\n",
            "javascript": "const fs = require('fs');\nconst text = fs.readFileSync(0, 'utf8').trim();\n// Yığın kullanarak parantezleri kontrol edin.\nconsole.log('YES');\n",
        },
        "cases": [
            {"input": "([]{})\n", "expected": "YES", "public": True},
            {"input": "([)]\n", "expected": "NO", "public": True},
            {"input": "\n", "expected": "YES", "public": False},
            {"input": "((\n", "expected": "NO", "public": False},
            {"input": "}\n", "expected": "NO", "public": False},
            {"input": "([])" * 200 + "\n", "expected": "YES", "public": False},
        ],
    },
    "merge-intervals": {
        "title": "Çakışan Aralıklar",
        "difficulty": "Orta",
        "statement": "İlk satır n, sonraki n satır başlangıç ve bitiş değeridir. Çakışan veya uçları aynı olan kapalı aralıkları birleştirip başlangıca göre sıralı, her satırda bir aralık olarak yazdırın. n=0 için çıktı boştur.",
        "constraints": "0 ≤ n ≤ 100; −10⁶ ≤ başlangıç ≤ bitiş ≤ 10⁶",
        "version": 1,
        "starters": {
            "python": "n = int(input())\nintervals = [tuple(map(int, input().split())) for _ in range(n)]\n# Sırala, birleştir, yazdır.\n",
            "javascript": "const fs = require('fs');\nconst nums = fs.readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\n// Aralıkları sırala ve birleştir.\n",
        },
        "cases": [
            {"input": "3\n1 3\n2 6\n8 10\n", "expected": "1 6\n8 10", "public": True},
            {"input": "0\n", "expected": "", "public": False},
            {"input": "3\n4 5\n1 4\n-2 -1\n", "expected": "-2 -1\n1 5", "public": False},
            {"input": "3\n1 10\n2 3\n1 10\n", "expected": "1 10", "public": False},
        ],
    },
}


def public_problems():
    return [
        {
            "id": key,
            **{k: v for k, v in p.items() if k != "cases"},
            "samples": [c for c in p["cases"] if c["public"]],
            "test_count": len(p["cases"]),
        }
        for key, p in PROBLEMS.items()
    ]
