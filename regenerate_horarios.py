#!/usr/bin/env python3
"""
Script de régénération des fichiers AUTO avec feuille Horarios.
Usage: python3 regenerate_horarios.py
"""
import sys
import os

# Ensure imports work
sys.path.insert(0, os.path.dirname(__file__))

import excel_export as ee

def main():
    print("=== Régénération des fichiers AUTO avec Horarios ===\n")
    
    # Generate both semesters
    result = ee.generate_all()
    
    if result['ok']:
        print("\n✅ Génération réussie!\n")
        print("Fichiers générés:")
        for f in result['files']:
            print(f"  • {f}")
        print("\nCes fichiers contiennent la feuille 'Horarios' avec:")
        print("  - Cours magistraux (MAT I, QUIM, FIS I...) — fond gris")
        print("  - Laboratoires planifiés — fond vert")
        print("  - Collisions détectées — fond rouge avec ⚠")
    else:
        print("\n❌ Erreur lors de la génération:")
        print(result.get('error', 'Unknown error'))
        if result.get('log'):
            print("\nLog:")
            print(result['log'])
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
