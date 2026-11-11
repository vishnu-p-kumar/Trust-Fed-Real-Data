package main

import (
  "encoding/json"
  "fmt"
  "time"
  "github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartGridContract struct { contractapi.Contract }
type UpdateCommitment struct {
  RoundID string `json:"roundId"`
  ClientID string `json:"clientId"`
  UpdateHash string `json:"updateHash"`
  ModelVersion int `json:"modelVersion"`
  Timestamp string `json:"timestamp"`
}
func (s *SmartGridContract) RecordUpdate(ctx contractapi.TransactionContextInterface, roundID, clientID, updateHash string, modelVersion int) error {
  if roundID=="" || clientID=="" || len(updateHash)!=64 || modelVersion<0 { return fmt.Errorf("invalid update commitment") }
  key,err:=ctx.GetStub().CreateCompositeKey("UPDATE",[]string{roundID,clientID}); if err!=nil{return err}
  exists,err:=ctx.GetStub().GetState(key); if err!=nil{return err}; if exists!=nil{return fmt.Errorf("update commitment already exists")}
  record:=UpdateCommitment{RoundID:roundID,ClientID:clientID,UpdateHash:updateHash,ModelVersion:modelVersion,Timestamp:time.Now().UTC().Format(time.RFC3339Nano)}
  body,err:=json.Marshal(record); if err!=nil{return err}
  return ctx.GetStub().PutState(key,body)
}
func (s *SmartGridContract) ReadUpdate(ctx contractapi.TransactionContextInterface, roundID, clientID string) (*UpdateCommitment,error) {
  key,err:=ctx.GetStub().CreateCompositeKey("UPDATE",[]string{roundID,clientID}); if err!=nil{return nil,err}
  body,err:=ctx.GetStub().GetState(key); if err!=nil{return nil,err}; if body==nil{return nil,fmt.Errorf("not found")}
  var result UpdateCommitment; if err=json.Unmarshal(body,&result); err!=nil{return nil,err}; return &result,nil
}
func main(){ chaincode,err:=contractapi.NewChaincode(&SmartGridContract{}); if err!=nil{panic(err)}; if err=chaincode.Start(); err!=nil{panic(err)} }
