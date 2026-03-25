# Odoo Kassa Integratie (Team Kassa)

Dit project bevat de infrastructuur en bestandsstructuur voor de "Kassa" module van het Integratieproject Desideriushogeschool 2026. Het project is zo opgezet dat alle teamleden lokaal een Odoo- en Postgres-instantie kunnen draaien, gekoppeld aan een eigen Python-integratiecontainer.

Volgens de architectuurregels schrijven we **géén code ín Odoo (geen modules)**. Alle scripts bevinden zich in de `integratie/` map en communiceren simpelweg via de XML-RPC API.

## 🚀 1. Opstarten van de omgeving (Docker)

1. Clone deze repository.
2. Zorg dat je een `.env` bestand in de hoofdmap hebt (vraag aan het team als je deze niet hebt, of bekijk de placeholders).
3. Start alle services op de achtergrond:
   ```bash
   docker-compose up -d --build
   ```

De volgende containers worden nu gestart:

- `kassa-db` (Postgres database)
- `kassa-web` (Odoo 17)
- `kassa-integratie` (Onze Python runtime waar we onze scripts bouwen)

## ⚙️ 2. Odoo Database Initialiseren

Omdat we lokaal werken met een verse setup, moet je éénmalig de initiële database bouwen in Odoo:

1. Open je browser en ga naar de localhost dat in de .env staat.
2. Odoo opent met het "Create Database" scherm. Vul exact deze gegevens in:
   - **Database Name:** van de .env
   - **Email:** van de .env
   - **Password:** van de .env
   - **Language / Country:** Naar keuze (Bv. English / Belgium).
   - **Demo data:** Vink dit aan als je test-producten en dummy-klanten wil inladen.
3. Klik op **Create database**. Na ongeveer één minuut zie je het Odoo-dashboard.

_(Installeer daarna de "Point of Sale" (Kassa) App in het Apps menu van Odoo!)_

## ✅ 3. De Connectie Testen

Zodra je in het Odoo dashboard zit, kan je controleren of onze `kassa-integratie` Python-container succesvol met Odoo kan communiceren via XML-RPC. Dit doen we met een handig ping script.

Voer in je terminal in de hoofdmap van het project dit commando uit:

```bash
docker-compose exec kassa-integratie python ping_odoo.py
```

Als alles klopt, zie je de boodschap:

> `✅ Authenticatie geslaagd!`  
> `De XML-RPC verbinding werkt perfect. Integratiescripts kunnen veilig data ophalen en wegschrijven!`

## 💻 4. Verder Ontwikkelen

Alle Python ontwikkeling van het team (`sender.py`, `receiver.py`, `poller.py` etc.) doen we in de map **`/integratie`**.

- De container `kassa-integratie` draait constant een loop op de achtergrond (`main.py`) zodat hij niet crasht.
- Wijzigingen in de code kun je lokaal testen door in de container een commando uit te voeren:
  ```bash
  docker-compose exec kassa-integratie bash
  ```
  _(Of je kan simpelweg losse scripts triggeren via `docker-compose exec kassa-integratie python scriptnaam.py`)_
- Afhankelijkheden (zoals `pika`) voeg je toe aan `integratie/requirements.txt`. (Vergeet na het toevoegen niet de container te herbouwen via `docker-compose build`).

## 🔄 5. CI/CD & Updates (Lokaal Deployen)

Dit project maakt gebruik van GitHub Actions voor onze **Continuous Integration (CI)**.
Bij elke `push` naar de `dev` of `prod` branch worden de tests (`pytest`), type checking (`mypy`, statische types controleren) en linting (`flake8`, controleren van code syntax) automatisch in de cloud uitgevoerd. Hierdoor ben je zeker dat de code naar behoren werkt.

Omdat we momenteel geen externe server of clouddienst gebruiken, doen we de **deployment simpelweg lokaal**. 
Wil je de nieuwste, geteste code van het team hebben en de integratie starten? Dan open je je terminal in de hoofdmap en voer je dit in:

```bash
git pull
docker-compose up -d --build
```

*(Dit commando trekt je laatste wijzigingen binnen, bouwt de integratiecontainers opnieuw op basis van je requirements/code en laat ze netjes op de achtergrond draaien, dit alles vanzelf!)*
