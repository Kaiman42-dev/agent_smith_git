import asyncio

async def tache(nom, duree):
    print(f"Debut: {nom}")
    await asyncio.sleep(duree)
    print(f"Fin: {nom}")

async def main():
    await tache("A", 2)
    
    await tache("B", 1)

asyncio.run(main())