from app.core.firebase import db

def check_reports():
    reports = db.collection("reports").order_by("created_at", direction="DESCENDING").limit(5).stream()
    for doc in reports:
        d = doc.to_dict()
        print(f"ID: {doc.id}")
        print(f"  Name: {d.get('file_name')}")
        print(f"  Status: {d.get('status')}")
        print(f"  Error Detail: {d.get('error_detail')}")
        print("-" * 20)

if __name__ == "__main__":
    check_reports()
