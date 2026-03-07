# Altered Draft Tool

Outil de draft interactif pour **Altered TCG**, conçu pour du contenu YouTube.

## Fonctionnalités

- Upload d'un export de collection Altered (ZIP contenant des fichiers JSON)
- Draft de 40 cartes + 1 héros avec choix à chaque étape
- Pick 1 : choix de faction parmi 3 rares de factions différentes
- Picks 2-39 : mix aléatoire de rares et communes/exaltées (15 rares, 24 communes/exaltées)
- Pick 40 : choix du héros
- Respect des règles officielles (max 3 copies, max 15 rares, pas d'uniques, pas de bannies)
- Export du deck final en .txt

## Lancer en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déploiement

Déployable sur [Streamlit Cloud](https://streamlit.io/cloud) en connectant ce dépôt GitHub.

## Structure

```
├── app.py               # UI Streamlit
├── draft_engine.py      # Logique de draft pure
├── requirements.txt
├── .gitignore
└── README.md
```
